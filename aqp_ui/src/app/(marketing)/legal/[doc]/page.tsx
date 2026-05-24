import type { Metadata } from "next";
import { notFound } from "next/navigation";

interface PageProps {
  params: Promise<{ doc: string }>;
}

interface LegalDoc {
  slug: string;
  title: string;
  description: string;
  effectiveDate: string;
  sections: { heading: string; body: string }[];
}

const LEGAL_DOCS: Record<string, LegalDoc> = {
  terms: {
    slug: "terms",
    title: "Terms of Service",
    description: "Terms governing your use of the Agentic Quant Platform.",
    effectiveDate: "2026-05-24",
    sections: [
      {
        heading: "1. Acceptance",
        body: "By creating an AQP account you accept these terms. If you are signing up on behalf of an organization, you represent that you have authority to bind that organization.",
      },
      {
        heading: "2. Permitted use",
        body: "AQP is a quantitative finance platform. You may use it to research, backtest, paper-trade, and live-trade financial strategies. You may not use it to facilitate market manipulation, fraud, or any illegal activity.",
      },
      {
        heading: "3. Account and tenancy",
        body: "Each customer account is provisioned as an organization with its own tenancy isolation. You are responsible for managing membership and access within your organization.",
      },
      {
        heading: "4. Data ownership",
        body: "You retain all rights to data you upload to AQP. We hold a limited license to process that data only to provide the service to you.",
      },
      {
        heading: "5. Brokerage credentials",
        body: "Brokerage credentials you enrol are envelope-encrypted in our vault and used only to execute orders on your behalf. We never use your credentials for anything outside the scope you authorize.",
      },
      {
        heading: "6. Termination",
        body: "You may cancel your account at any time. We may suspend or terminate accounts that violate these terms with reasonable notice except in cases of imminent harm.",
      },
    ],
  },
  privacy: {
    slug: "privacy",
    title: "Privacy Policy",
    description: "How AQP collects, uses, and protects your data.",
    effectiveDate: "2026-05-24",
    sections: [
      {
        heading: "1. Data we collect",
        body: "Account information (email, name, organization). Usage data (which features you use, error logs). Strategy and trading data you upload. We do not sell or share your data with third parties for marketing.",
      },
      {
        heading: "2. Authentication providers",
        body: "If you sign in with Auth0 or Microsoft Entra ID, those providers process authentication credentials per their own privacy policies.",
      },
      {
        heading: "3. Brokerage credentials",
        body: "Brokerage API keys are envelope-encrypted before persistence and never returned to your browser. AQP staff cannot read your raw credentials.",
      },
      {
        heading: "4. Data isolation",
        body: "Your data is isolated from other tenants using PostgreSQL row-level security (Free / Pro), schema-per-tenant (Team), or dedicated database (Enterprise).",
      },
      {
        heading: "5. Sub-processors",
        body: "AQP uses Auth0 (identity), AWS (infrastructure), HashiCorp Vault (secrets), and Stripe (billing) as sub-processors. The current list is available on request.",
      },
      {
        heading: "6. Your rights",
        body: "GDPR / CCPA: you may request export, correction, or deletion of your personal data at any time by emailing privacy@aqp.fund.",
      },
    ],
  },
  security: {
    slug: "security",
    title: "Security",
    description: "How AQP secures your data and credentials.",
    effectiveDate: "2026-05-24",
    sections: [
      {
        heading: "Encryption at rest",
        body: "All databases use AES-256-GCM at the storage layer. Brokerage credentials are envelope-encrypted with per-tenant KEKs in HashiCorp Vault Transit (or your cloud KMS for Enterprise tier).",
      },
      {
        heading: "Encryption in transit",
        body: "TLS 1.3 everywhere. HSTS with preload. Strict CSP. WebSocket connections use the same TLS termination.",
      },
      {
        heading: "Authentication",
        body: "Auth0 and Microsoft Entra ID for SSO. Step-up MFA (RFC 9470) on all destructive operations. JWE-encrypted session cookies — never JWT-in-localStorage.",
      },
      {
        heading: "Compliance",
        body: "SOC 2 Type II in progress. ISO 27001 on the roadmap. HIPAA BAA available for Enterprise tier. Contact security@aqp.fund for our latest audit report.",
      },
    ],
  },
  dpa: {
    slug: "dpa",
    title: "Data Processing Addendum",
    description: "GDPR / CCPA compliant data processing terms.",
    effectiveDate: "2026-05-24",
    sections: [
      {
        heading: "Roles",
        body: "Customer is the data controller; AQP is the data processor. AQP processes personal data only on documented instructions from Customer.",
      },
      {
        heading: "Sub-processors",
        body: "AQP maintains a list of sub-processors at /legal/sub-processors. Customers receive 30 days notice before new sub-processors are added.",
      },
      {
        heading: "Data location",
        body: "Default region: us-east-1 (AWS). EU customers can request EU residency (eu-central-1). Enterprise customers can request dedicated single-region deployment.",
      },
      {
        heading: "Breach notification",
        body: "AQP notifies Customer within 72 hours of confirming a data breach affecting Customer's personal data.",
      },
    ],
  },
  contact: {
    slug: "contact",
    title: "Contact",
    description: "Get in touch with the AQP team.",
    effectiveDate: "2026-05-24",
    sections: [
      {
        heading: "Sales",
        body: "Email: sales@aqp.fund. We'll respond within one business day.",
      },
      {
        heading: "Support",
        body: "Email: support@aqp.fund. Free tier: community Discord. Pro: 24h. Team: 4h. Enterprise: 1h SLA.",
      },
      {
        heading: "Security disclosures",
        body: "Email: security@aqp.fund. PGP key on request. Please report responsibly; we appreciate the heads-up.",
      },
      {
        heading: "Privacy",
        body: "Email: privacy@aqp.fund.",
      },
    ],
  },
};

export async function generateStaticParams(): Promise<{ doc: string }[]> {
  return Object.keys(LEGAL_DOCS).map((doc) => ({ doc }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { doc } = await params;
  const entry = LEGAL_DOCS[doc];
  if (!entry) return { title: "Legal" };
  return { title: entry.title, description: entry.description };
}

export const dynamic = "force-static";
export const revalidate = 86400;

export default async function LegalDocPage({ params }: PageProps) {
  const { doc } = await params;
  const entry = LEGAL_DOCS[doc];
  if (!entry) notFound();

  return (
    <div className="mx-auto max-w-3xl px-6 py-20">
      <h1 className="text-4xl font-bold" style={{ color: "var(--text-primary)" }}>
        {entry.title}
      </h1>
      <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
        Effective {new Date(entry.effectiveDate).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}
      </p>
      <div className="mt-8 space-y-6">
        {entry.sections.map((section) => (
          <section key={section.heading}>
            <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
              {section.heading}
            </h2>
            <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              {section.body}
            </p>
          </section>
        ))}
      </div>
    </div>
  );
}
