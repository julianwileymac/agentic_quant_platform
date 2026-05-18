# Microsoft Entra ID Through Auth0 (2026) Best Practices

For your architecture (Auth0 as the only app-facing OIDC provider), the clean approach is:

1. configure Microsoft Entra ID as an **Auth0 Enterprise Connection**,
2. keep app auth flows pointed at Auth0 Universal Login,
3. optionally force that enterprise connection from React via `connection=...`,
4. map Entra tenant ID (`tid`) into namespaced Auth0 token claims using Actions,
5. let FastAPI map that tenant claim into your `Organization` domain model (AQP-style `EntraTenantLink` flow).

## 1) Enterprise vs Social Microsoft connection

Use **Enterprise (Azure AD / Entra ID)** when you need workforce identities (work/school accounts, tenant policies, conditional access, B2B).  
Use **Social Microsoft** only for consumer Microsoft accounts (MSA / live.com) and lightweight sign-in experiences.

For B2B quant platform tenants, Enterprise Connection is the correct default.

## 2) Triggering "Continue with Microsoft" from React

You can let Universal Login render the Microsoft button naturally, or explicitly force it:

```tsx
import { useAuth0 } from "@auth0/auth0-react";

export function SignInWithMicrosoftButton() {
  const { loginWithRedirect } = useAuth0();

  return (
    <button
      onClick={() =>
        loginWithRedirect({
          authorizationParams: {
            connection: "azure-ad-myorg",
            audience: "https://api.your-company.com",
            scope: "openid profile email",
          },
        })
      }
    >
      Continue with Microsoft
    </button>
  );
}
```

This still goes through Auth0-hosted login and callback handling.

## 3) Universal Login customization vs custom login app

In 2026, Universal Login remains the preferred enterprise posture:
- stronger default security envelope,
- centralized factor/session handling,
- easier branding and domain consistency (especially with Custom Domains),
- lower long-term maintenance than bespoke embedded credential UI.

Custom login screens are justified only when product UX constraints cannot be met with Universal Login + templates/partials/actions.

## 4) Multi-tenant Entra registration pattern

For multi-tenant B2B onboarding:
- register Entra app as multi-tenant where appropriate,
- configure Auth0 Azure AD Enterprise Connection accordingly (tenant-specific vs common endpoint model),
- verify redirect URI and consent policies across onboarding tenants,
- keep allow-list / explicit linkage in your own app domain model.

Do not let raw `tid` automatically create unrestricted tenants. Require an admin-controlled linkage step.

## 5) Map `tid` to custom claim via Auth0 Actions

Add a Post-Login Action to project Entra tenant identity into Auth0 tokens:

```js
// Auth0 Action: Post Login
exports.onExecutePostLogin = async (event, api) => {
  const tenantId = event.user?.tenantid || event.user?.tid;
  if (!tenantId) return;

  api.accessToken.setCustomClaim("https://aqp.example.com/tenant_id", tenantId);
  api.idToken.setCustomClaim("https://aqp.example.com/tenant_id", tenantId);
};
```

Use your own namespace URL (never Auth0-owned domains).

## 6) FastAPI side: enforce linkage (AQP rule-44 style)

At API authorization time:
1. validate Auth0 token (`iss`, `aud`, signature, expiry),
2. read `https://aqp.example.com/tenant_id`,
3. resolve `tenant_id -> Organization` through your linkage table (`EntraTenantLink`),
4. deny or mark pending when unknown tenant is encountered.

This preserves "Auth0 as control plane" while keeping tenant authorization decisions in your platform database.

## 7) Operational caveats

- Keep enterprise connection names stable once used in frontend code.
- Test both IdP-initiated and SP-initiated sign-in.
- Ensure claim size discipline; only include stable tenant identifiers in tokens.
- Maintain clear "pending tenant link" UX for first login from unknown enterprise tenants.

---

## Sources

- https://auth0.com/docs/authenticate/identity-providers/enterprise-identity-providers/azure-active-directory/v2
- https://auth0.com/blog/deciding-between-social-enterprise-connection/
- https://auth0.com/docs/get-started/auth0-overview/create-tenants/multi-tenant-apps-best-practices
- https://auth0.com/docs/secure/tokens/json-web-tokens/create-custom-claims
- https://auth0.com/blog/adding-custom-claims-to-id-token-with-auth0-actions/
- https://auth0.com/docs/customize/login-pages
- https://learn.microsoft.com/en-us/entra/identity-platform/howto-convert-app-to-be-multi-tenant
