package aqp.ingest.mutating_tool

# Reject mutating ingestion-plane tool calls that lack a recent
# step-up MFA assertion. Mirrors the FastAPI Depends gate so the
# policy is also verifiable from offline audit dumps.
#
# Input shape:
#   { tool_id: "data.ingest.create_connection",
#     actor_kind: "user" | "agent" | "service",
#     mfa_age_seconds: 120 }

default allow = false

allow {
    not is_mutating_tool
}

allow {
    is_mutating_tool
    input.actor_kind == "agent"  # agents go through approval workflow instead
}

allow {
    is_mutating_tool
    input.actor_kind == "user"
    input.mfa_age_seconds <= 180
}

is_mutating_tool {
    startswith(input.tool_id, "data.ingest.")
    not endswith(input.tool_id, ".list_templates")
    not endswith(input.tool_id, ".preview_source")
}

is_mutating_tool {
    startswith(input.tool_id, "data.transform.")
}

is_mutating_tool {
    startswith(input.tool_id, "data.ratelimit.")
    endswith(input.tool_id, ".policy.update")
}
