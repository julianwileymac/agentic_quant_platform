# Break-glass runbook

Procedure for assuming the `AqpAdminBreakGlassRole` during an
incident.

The role is **only** to be used when:

1. Normal operator pathways (KillSwitch, scoped admin roles) have
   failed.
2. A documented incident ticket exists.
3. **Two named operators** are available (4-eyes principle).

## Mechanics

- The role itself carries no permissions until an
  `AdministratorAccess`-attaching Lambda runs.
- The attach is triggered by the second operator's approval
  through `aqp_admin/services/break_glass.py`.
- The session has a **hard 60-minute auto-expiry** enforced by
  EventBridge calling the detach Lambda.
- Every API call while the role is active is reported to Security
  Hub as a HIGH-severity finding.

## Steps

### Operator A — file the request

1. Open `/admin/accounts` in the admin UI.
2. Click **"Break-glass request"** (visible only to users with
   the `aqp-superadmin` role).
3. Fill in:
   - **Reason** (free-text, mandatory).
   - **Incident id** (Linear / Sentry / PagerDuty link).
   - **Duration** (max 60 minutes).
4. Submit. The request lands in the audit ledger as
   `admin.break_glass.request`.

### Operator B — approve

1. Watch for the Slack notification from the
   `#aqp-security-incidents` channel.
2. Open the request URL the notification links to.
3. Verify Operator A's reason + incident id.
4. Click **"Approve"**. Step-up MFA is required.
5. The Lambda fires and attaches `AdministratorAccess` to the
   target role. Audit row:
   `admin.break_glass.approve` -> `admin.break_glass.attach`.

### Operator A — perform the action

1. `aws sts assume-role --role-arn <break-glass-role-arn> \
        --role-session-name "incident-<id>"`.
2. Carry out the minimum action required.
3. The session SHOULD be terminated early via the admin UI's
   **"Detach"** button as soon as the action completes.

### Auto-expiry

If 60 minutes elapse, EventBridge invokes the detach Lambda
automatically. Audit row: `admin.break_glass.expire`.

## Post-incident

- Both operators sign the post-incident review.
- Security officer reviews the Security Hub findings + audit
  trail within 24h.
- Anything done while the role was active is reproduced in a
  small, scoped follow-up PR if it should be permanent.
