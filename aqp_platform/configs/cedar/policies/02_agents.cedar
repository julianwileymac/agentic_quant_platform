// =============================================================================
// Agent-sandbox tool authorization.
//
// Phase 4 §7.3 + Phase 5 §8.1 (RESTRUCTURING_PLAN.md). The agent
// sandbox pool runs LLM-emitted code under gVisor RuntimeClass
// (Phase 2 §5.3 Kyverno policy `02-require-runtime-class`). When an
// agent invokes an MCP tool, the tool's HTTP handler resolves the
// agent's identity via the OAuth 2.0 token-exchange broker (Rule 54)
// and asks Cedar: "may this agent, acting on behalf of this user,
// invoke this tool with these arguments?"
//
// Entity model:
//   Agent     — agent runtime instance. Attributes: agent_id,
//                on_behalf_of, capabilities[], gvisor_class.
//   Tool      — MCP tool descriptor. Attributes: descriptor_hash,
//                mutates (bool), required_capability,
//                audience.
//   Action    — Action::"invoke_tool"
//                Action::"read_secret"
//                Action::"write_outbox"
// =============================================================================

// ------------------------------------------------------------------
// 1. Agents may invoke read-only tools whose required capability is
//    in the agent's capability bag.
// ------------------------------------------------------------------
permit (
  principal,
  action == Action::"invoke_tool",
  resource is Tool
)
when {
  principal has capabilities
  && resource has required_capability
  && principal.capabilities.contains(resource.required_capability)
  && resource has mutates
  && resource.mutates == false
};

// ------------------------------------------------------------------
// 2. Mutating tools require: (a) capability match, AND (b) explicit
//    approval already recorded for this (agent, on_behalf_of, tool)
//    triple. The approval check lives in `aqp/agents/runtime.py`;
//    Cedar enforces the capability gate at the entry point.
// ------------------------------------------------------------------
permit (
  principal,
  action == Action::"invoke_tool",
  resource is Tool
)
when {
  principal has capabilities
  && resource has required_capability
  && principal.capabilities.contains(resource.required_capability)
  && resource has mutates
  && resource.mutates == true
  && resource has approval_id
  && resource.approval_id != ""
};

// ------------------------------------------------------------------
// 3. Agents may NOT read raw secret material; they go through the
//    BrokerCredentialStore (Rule 55) which mints scoped tokens.
//    The forbid below is the belt-and-braces gate so a misconfigured
//    tool descriptor can never reach `data.secrets.read`.
// ------------------------------------------------------------------
forbid (
  principal,
  action == Action::"read_secret",
  resource
)
when {
  principal is Agent
};

// ------------------------------------------------------------------
// 4. gVisor-runtime requirement. Agents not flagged as
//    `gvisor_class=gvisor` may not invoke high-risk tools.
// ------------------------------------------------------------------
forbid (
  principal,
  action == Action::"invoke_tool",
  resource is Tool
)
when {
  resource has required_runtime
  && resource.required_runtime == "gvisor"
  && (!(principal has gvisor_class) || principal.gvisor_class != "gvisor")
};
