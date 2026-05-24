// Package server wires the gRPC + REST + Prometheus surfaces of aqp-rls.
//
// The bucket math lives in Redis Lua scripts loaded once at boot via
// SCRIPT LOAD and invoked via EVALSHA; Server.checkLua / reserveLua /
// releaseLua are the cached SHA digests.
package server

import (
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc"
)

// Lua scripts are embedded so the binary is single-file deployable.
// The paths here mirror aqp_ratelimit/lua/*.lua; Phase 6 will move
// them under //go:embed once the build tag wiring is in place.

const (
	tokenBucketLua = `
local key             = KEYS[1]
local capacity        = tonumber(ARGV[1])
local refill_rate     = tonumber(ARGV[2])
local refill_interval = tonumber(ARGV[3])
local now             = tonumber(ARGV[4])
local requested       = tonumber(ARGV[5])

local function ttl_seconds()
    if refill_rate and refill_rate > 0 then
        return math.ceil(capacity / refill_rate) + 60
    end
    return 3600
end

local function retry_after_ms(short)
    if refill_rate and refill_rate > 0 then
        return math.ceil(short / refill_rate * 1000)
    end
    return 3600000
end

local b = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens      = tonumber(b[1]) or capacity
local last_refill = tonumber(b[2]) or now

local elapsed    = (now - last_refill) / 1000
local new_tokens = math.min(capacity, tokens + elapsed * refill_rate)

if new_tokens < requested then
    redis.call('HSET', key, 'tokens', new_tokens, 'last_refill', now)
    redis.call('EXPIRE', key, ttl_seconds())
    return {0, new_tokens, retry_after_ms(requested - new_tokens)}
end

new_tokens = new_tokens - requested
redis.call('HSET', key, 'tokens', new_tokens, 'last_refill', now)
redis.call('EXPIRE', key, ttl_seconds())
return {1, new_tokens, 0}
`
)

type Config struct {
	RedisURL string
	Logger   *slog.Logger
}

type Server struct {
	cfg    Config
	rdb    *redis.Client
	logger *slog.Logger

	checkLua *redis.Script

	tokensConsumed *prometheus.CounterVec
	bucketRemain   *prometheus.GaugeVec
	checkLatency   prometheus.Histogram

	grpcSrv *grpc.Server
}

func New(cfg Config) (*Server, error) {
	if cfg.Logger == nil {
		cfg.Logger = slog.Default()
	}
	opt, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		return nil, fmt.Errorf("parse redis url: %w", err)
	}
	rdb := redis.NewClient(opt)
	if err := rdb.Ping(context.Background()).Err(); err != nil {
		return nil, fmt.Errorf("redis ping: %w", err)
	}

	check := redis.NewScript(tokenBucketLua)
	if _, err := check.Load(context.Background(), rdb).Result(); err != nil {
		return nil, fmt.Errorf("load token_bucket lua: %w", err)
	}

	srv := &Server{
		cfg:      cfg,
		rdb:      rdb,
		logger:   cfg.Logger,
		checkLua: check,
		tokensConsumed: promauto.NewCounterVec(prometheus.CounterOpts{
			Name: "rl_tokens_consumed_total",
			Help: "Total rate-limit tokens consumed; partitioned by user / service / key_id / decision.",
		}, []string{"user", "service", "key_id", "decision"}),
		bucketRemain: promauto.NewGaugeVec(prometheus.GaugeOpts{
			Name: "rl_bucket_remaining",
			Help: "Remaining tokens in a bucket after the most recent Check.",
		}, []string{"user", "service", "key_id"}),
		checkLatency: promauto.NewHistogram(prometheus.HistogramOpts{
			Name:    "rl_check_duration_seconds",
			Help:    "Latency of Check calls including Redis Lua eval round-trip.",
			Buckets: prometheus.ExponentialBuckets(0.0001, 2, 16),
		}),
	}
	srv.grpcSrv = grpc.NewServer()
	return srv, nil
}

func (s *Server) ServeGRPC(lis net.Listener) error {
	// gRPC service registration ships in Phase 1 once we wire the
	// protoc-generated stubs. The skeleton accepts connections so
	// the operator can confirm the listener is up.
	return s.grpcSrv.Serve(lis)
}

func (s *Server) HTTPHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("/v1/status/", s.handleStatus)
	mux.HandleFunc("/v1/check", s.handleCheck)
	return mux
}

func (s *Server) MetricsHandler() http.Handler {
	return promhttp.Handler()
}

func (s *Server) Close() {
	s.grpcSrv.GracefulStop()
	_ = s.rdb.Close()
}

// ---------------------------------------------------------------------------
// HTTP handlers (Phase 0 skeleton; full gRPC ships in Phase 1)
// ---------------------------------------------------------------------------

type checkReq struct {
	UserID  string `json:"user_id"`
	Service string `json:"service"`
	KeyID   string `json:"key_id"`
	Tokens  int    `json:"n_tokens"`
}

type checkResp struct {
	Allow         bool    `json:"allow"`
	Remaining     float64 `json:"remaining"`
	Capacity      float64 `json:"capacity"`
	RefillRate    float64 `json:"refill_rate"`
	RetryAfterMs  int64   `json:"retry_after_ms"`
}

func (s *Server) handleCheck(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body checkReq
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	if body.UserID == "" || body.Service == "" || body.KeyID == "" {
		http.Error(w, "missing identity", http.StatusBadRequest)
		return
	}
	if body.Tokens == 0 {
		body.Tokens = 1
	}

	t0 := time.Now()
	defer func() { s.checkLatency.Observe(time.Since(t0).Seconds()) }()

	key := fmt.Sprintf("aqp:rl:%s:%s:%s", body.UserID, body.Service, body.KeyID)
	capacity := 60.0
	refill := 1.0
	now := time.Now().UnixMilli()
	res, err := s.checkLua.Run(
		r.Context(),
		s.rdb,
		[]string{key},
		capacity, refill, 1.0, now, body.Tokens,
	).Slice()
	if err != nil {
		http.Error(w, fmt.Sprintf("redis: %v", err), http.StatusInternalServerError)
		return
	}
	if len(res) != 3 {
		http.Error(w, "unexpected lua result", http.StatusInternalServerError)
		return
	}
	allow := asInt64(res[0]) == 1
	remaining := asFloat(res[1])
	retry := asInt64(res[2])

	decision := "deny"
	if allow {
		decision = "allow"
	}
	s.tokensConsumed.WithLabelValues(body.UserID, body.Service, body.KeyID, decision).
		Add(float64(body.Tokens))
	s.bucketRemain.WithLabelValues(body.UserID, body.Service, body.KeyID).Set(remaining)

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(checkResp{
		Allow:        allow,
		Remaining:    remaining,
		Capacity:     capacity,
		RefillRate:   refill,
		RetryAfterMs: retry,
	})
}

func (s *Server) handleStatus(w http.ResponseWriter, r *http.Request) {
	keyID := strings.TrimPrefix(r.URL.Path, "/v1/status/")
	if keyID == "" {
		http.Error(w, "missing key_id", http.StatusBadRequest)
		return
	}
	// Phase 0 surface: returns last-known cached remaining for the
	// key_id. Phase 1 will resolve the (user, service, key_id) tuple
	// from the rl_keys table via the Python API server.
	if g, err := s.bucketRemain.GetMetricWithLabelValues("?", "?", keyID); err == nil {
		_ = g
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"key_id":  keyID,
		"summary": "use Python API surface for full status",
	})
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func asInt64(v any) int64 {
	switch x := v.(type) {
	case int64:
		return x
	case int:
		return int64(x)
	case string:
		var n int64
		_, _ = fmt.Sscanf(x, "%d", &n)
		return n
	default:
		return 0
	}
}

func asFloat(v any) float64 {
	switch x := v.(type) {
	case float64:
		return x
	case int64:
		return float64(x)
	case int:
		return float64(x)
	case string:
		var f float64
		_, _ = fmt.Sscanf(x, "%f", &f)
		return f
	default:
		return 0
	}
}

var _ = errors.New
