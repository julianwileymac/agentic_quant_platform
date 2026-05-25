/**
 * Auth0 Action — outbound SCIM provisioning to AWS IAM Identity Center
 * and Microsoft Graph (Entra ID).
 *
 * Trigger: post-user-registration + Event Streams (user.updated /
 * user.deleted from the Auth0 Management API).
 *
 * Phase 1.5 of the AQP control-plane maturation. Skeleton only —
 * the actual SCIM payload shapes ship in a follow-up PR. This file
 * exists so the Terraform module under
 * aqp_platform/terraform/modules/auth0/scim-outbound/ has a stable
 * source artifact to provision.
 *
 * Secrets schema (all values resolve through Auth0 Action Secrets;
 * the matching CredentialResolver entries live in the platform's
 * Vault namespace — never hard-coded here):
 *
 *   - SCIM_AWS_BEARER         AWS IAM Identity Center SCIM access token
 *   - SCIM_AWS_TENANT_URL     AWS SCIM endpoint base URL
 *   - GRAPH_TENANT_ID         Microsoft Entra tenant id
 *   - GRAPH_CLIENT_ID         Microsoft Graph app registration client id
 *   - GRAPH_CLIENT_SECRET     Microsoft Graph app registration client secret
 *
 * Per the always-on AQP management-engine rule
 * (.cursor/rules/aqp-management-engine.mdc) this Action MUST NOT
 * log secret values. The skeleton uses event.secrets.* directly and
 * never echoes them through console.log / event.cache writes.
 */

/**
 * @param {Event} event
 * @param {PostUserRegistrationAPI | PostLoginAPI} api
 */
exports.onExecutePostUserRegistration = async (event, api) => {
  // Skeleton: defer actual SCIM POST/PATCH to the follow-up PR.
  // The Action ships in inactive form (Terraform deploys it but
  // doesn't enable it on the Action chain) until the payload shapes
  // are reviewed.
  if (!event.user || !event.user.user_id) {
    return;
  }
  // Intentionally a no-op — real impl posts to:
  //   - SCIM_AWS_TENANT_URL/Users  (AWS IAM Identity Center)
  //   - https://graph.microsoft.com/v1.0/users  (Entra)
};

/**
 * Auth0 Event Streams handler (user.deleted) — mirror revoke into
 * IAM Identity Center + Graph. Skeleton.
 */
exports.onExecuteEventStream = async (event, api) => {
  if (!event || event.event_type !== "user.deleted") {
    return;
  }
  // Intentionally a no-op — real impl issues DELETE against the
  // matching SCIM resource ids tracked in
  // Auth0 user app_metadata.scim_external_ids.
};
