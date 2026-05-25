# Auth0 Outbound SCIM module (skeleton)

Phase 1.5 of the AQP control-plane maturation. Deploys an Auth0
Action that pushes user lifecycle events out to:

- AWS IAM Identity Center SCIM (`POST https://scim.{region}.amazonaws.com/{tenant}/scim/v2/Users`)
- Microsoft Graph (`POST https://graph.microsoft.com/v1.0/users`)

This module ships in **skeleton** form — the Action body in
[../../../../auth0/actions/scim-outbound.js](../../../../../auth0/actions/scim-outbound.js)
is a no-op until the SCIM payload shapes are reviewed. The skeleton
is useful today because:

1. The Auth0 Action exists and is wired through the same Terraform
   path as production secrets, so the rotation flow is exercised
   end-to-end.
2. The matching `aqp/auth/providers/msal_entra.py` provider can
   look up the Action id in Auth0 and bind it on demand once the
   payload work lands.
3. The credential schema is locked — Vault rotation hooks can
   target the named secrets immediately.

## Inputs

- `secrets` — map of Auth0 Action Secret name -> value. Resolve
  the values through `CredentialResolver` in the calling stack
  (NEVER hard-code secrets here). Expected keys are documented in
  [../../../../auth0/actions/scim-outbound.config.json](../../../../../auth0/actions/scim-outbound.config.json).
- `enable_action_binding` — bool. When true, binds the Action into
  the post-user-registration trigger chain. Defaults to false so
  the skeleton ships in deployed-but-inactive form.

## Outputs

- `action_id` — Auth0 Action id, for downstream binding.
- `action_name` — Action display name.
- `binding_active` — whether the post-user-registration binding is
  active.

## Operator runbook (rollout)

1. Deploy with `enable_action_binding = false` (default).
2. Verify the Action shows up in the Auth0 dashboard with the
   expected secrets schema.
3. Land the payload PR; review the SCIM body in stage against a
   throwaway IAM Identity Center tenant.
4. Flip `enable_action_binding = true` in the prod stack.
5. Monitor the Action's log stream — failures fan out via the
   existing `KillSwitch` topbar (the brokered `/admin/halt/all`).
