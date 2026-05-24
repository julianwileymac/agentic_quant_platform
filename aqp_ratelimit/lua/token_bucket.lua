-- Verbatim Redis token-bucket script per blueprint section 8.2.
--
-- KEYS[1]  = bucket key  "aqp:rl:{user_id}:{service}:{key_id}"
-- ARGV[1]  = capacity      (max tokens)
-- ARGV[2]  = refill_rate   (tokens / second)
-- ARGV[3]  = refill_interval (seconds; informational, not used)
-- ARGV[4]  = now_ms        (Unix epoch milliseconds)
-- ARGV[5]  = requested     (tokens this call wants)
--
-- Returns {allow, new_tokens, retry_after_ms} where allow in {0,1}.
--
-- Loaded once via SCRIPT LOAD; invoked via EVALSHA so the bucket
-- check sits on the synchronous request path without extra round
-- trips. Per Redis docs sub-millisecond latency is normal at
-- millions of QPS.

local key             = KEYS[1]
local capacity        = tonumber(ARGV[1])
local refill_rate     = tonumber(ARGV[2])
local refill_interval = tonumber(ARGV[3])
local now             = tonumber(ARGV[4])
local requested       = tonumber(ARGV[5])

-- TTL ceiling: when refill_rate <= 0 the bucket never refills;
-- pin the TTL to 1 hour so a stale key still expires cleanly.
local function ttl_seconds()
    if refill_rate and refill_rate > 0 then
        return math.ceil(capacity / refill_rate) + 60
    end
    return 3600
end

-- Retry-after when bucket is exhausted: when refill_rate <= 0
-- surface a 1-hour sentinel rather than dividing by zero.
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
