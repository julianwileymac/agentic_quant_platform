-- Release a previously-reserved batch of tokens back to its bucket.
--
-- Idempotent: releasing an already-released reservation is a no-op
-- (the key already expired or was explicitly released). Releasing
-- an unknown reservation is also a no-op.
--
-- KEYS[1] = reservation key "aqp:rl:rsv:{reservation_id}"
-- ARGV[1] = capacity
-- ARGV[2] = now_ms
--
-- Returns released_tokens (0 if no-op).

local rsv_key  = KEYS[1]
local capacity = tonumber(ARGV[1])
local now      = tonumber(ARGV[2])

local r = redis.call('HMGET', rsv_key, 'tokens', 'bucket_key')
local tokens     = tonumber(r[1])
local bucket_key = r[2]
if tokens == nil or bucket_key == nil then
    return 0
end

local b = redis.call('HMGET', bucket_key, 'tokens', 'last_refill')
local existing = tonumber(b[1]) or 0
local refunded = math.min(capacity, existing + tokens)
redis.call('HSET', bucket_key, 'tokens', refunded, 'last_refill', now)
redis.call('DEL', rsv_key)
return tokens
