package aqp.ingest.agent_quota

# Reject agent calls that would exceed the agent's per-month
# tool-invocation budget.
#
# Input shape:
#   { actor_kind: "agent",
#     agent_subject: "agent|preview",
#     calls_this_month: 1245,
#     max_calls_per_month: 5000 }

default allow = false

allow {
    input.actor_kind != "agent"
}

allow {
    input.actor_kind == "agent"
    input.calls_this_month < input.max_calls_per_month
}
