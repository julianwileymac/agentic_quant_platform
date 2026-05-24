// Command aqp-rls is the standalone AQP rate-limit Go service.
//
// Layout: gRPC server on the port set by AQP_RLS_GRPC_PORT (default
// :50051) speaking the protobuf in aqp_ratelimit/go-rls/proto. Side
// car HTTP server on AQP_RLS_HTTP_PORT (default :8080) exposing
// `/v1/status/{key_id}` and `/healthz`. Prometheus metrics on
// AQP_RLS_METRICS_PORT (default :9102) — rl_tokens_consumed_total,
// rl_bucket_remaining, rl_check_duration_seconds.
//
// The actual bucket math lives in Redis Lua (loaded from
// aqp_ratelimit/lua/{token_bucket,reserve,release}.lua); the Go
// service is a thin protocol adapter so the Python clients +
// Envoy filter can all converge on a single canonical
// implementation.
package main

import (
	"context"
	"flag"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/aqp/aqp_ratelimit/go-rls/internal/server"
)

func main() {
	flag.Parse()

	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	slog.SetDefault(logger)

	grpcAddr := envOr("AQP_RLS_GRPC_PORT", ":50051")
	httpAddr := envOr("AQP_RLS_HTTP_PORT", ":8080")
	metricsAddr := envOr("AQP_RLS_METRICS_PORT", ":9102")
	redisURL := envOr("AQP_RATELIMIT_REDIS_URL", "redis://localhost:6379/0")

	logger.Info("aqp-rls boot",
		slog.String("grpc", grpcAddr),
		slog.String("http", httpAddr),
		slog.String("metrics", metricsAddr),
		slog.String("redis", redisURL),
	)

	srv, err := server.New(server.Config{
		RedisURL: redisURL,
		Logger:   logger,
	})
	if err != nil {
		logger.Error("server.New failed", slog.Any("err", err))
		os.Exit(2)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// gRPC listener
	go func() {
		lis, err := net.Listen("tcp", grpcAddr)
		if err != nil {
			logger.Error("grpc listen failed", slog.Any("err", err))
			stop()
			return
		}
		if err := srv.ServeGRPC(lis); err != nil {
			logger.Error("grpc serve failed", slog.Any("err", err))
			stop()
		}
	}()

	// REST listener
	go func() {
		mux := srv.HTTPHandler()
		s := &http.Server{
			Addr:              httpAddr,
			Handler:           mux,
			ReadHeaderTimeout: 5 * time.Second,
		}
		if err := s.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("http serve failed", slog.Any("err", err))
			stop()
		}
	}()

	// Prometheus listener
	go func() {
		mux := srv.MetricsHandler()
		s := &http.Server{
			Addr:              metricsAddr,
			Handler:           mux,
			ReadHeaderTimeout: 5 * time.Second,
		}
		if err := s.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("metrics serve failed", slog.Any("err", err))
		}
	}()

	<-ctx.Done()
	logger.Info("aqp-rls shutting down")
	srv.Close()
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
