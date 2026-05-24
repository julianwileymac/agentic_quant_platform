-- Multi-token preflight reservation with TTL release.
--
-- Used by `aqp materialize --partition-range YYYY-MM-DD..YYYY-MM-DD`
-- to debit N tokens upfront for a large backfill. If the backfill
-- doesn't consume them within ttl_s seconds the reservation key
-- auto-expires and Redis quietly drops it.
--
-- KEYS[1] = bucket key      "aqp:rl:{user_id}:{service}:{key_id}"
-- KEYS[2] = reservation key "aqp:rl:rsv:{reservation_id}"
-- ARGV[1] = capacity
-- ARGV[2] = refill_rate     (tokens / second)
-- ARGV[3] = now_ms
-- ARGV[4] = requested       (tokens to reserve)
-- ARGV[5] = ttl_s           (reservation TTL in seconds)
-- ARGV[6] = reservation_id
--
-- Returns {allow, remaining, ttl_s} where allow in {0, 1}.

local bucket_key = KEYS[1]
local rsv_key    = KEYS[2]
local capacity   = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now         = tonumber(ARGV[3])
local requested   = tonumber(ARGV[4])
local ttl_s       = tonumber(ARGV[5])
local rsv_id      = ARGV[6]

local function ttl_seconds()
    if refill_rate and refill_rate > 0 then
        return math.ceil(capacity / refill_rate) + 60
    end
    return 3600
end

local b = redis.call('HMGET', bucket_key, 'tokens', 'last_refill')
local tokens      = tonumber(b[1]) or capacity
local last_refill = tonumber(b[2]) or now

local elapsed    = (now - last_refill) / 1000
local new_tokens = math.min(capacity, tokens + elapsed * refill_rate)

if new_tokens < requested then
    redis.call('HSET', bucket_key, 'tokens', new_tokens, 'last_refill', now)
    redis.call('EXPIRE', bucket_key, ttl_seconds())
    return {0, new_tokens, 0}
end

new_tokens = new_tokens - requested
redis.call('HSET', bucket_key, 'tokens', new_tokens, 'last_refill', now)
redis.call('EXPIRE', bucket_key, ttl_seconds())
redis.call('HSET', rsv_key,
    'tokens', requested,
    'bucket_key', bucket_key,
    'created_at', now)
redis.call('EXPIRE', rsv_key, ttl_s)
return {1, new_tokens, ttl_s}
