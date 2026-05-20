import { Link } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const CARDS = [
  { title: "Kubernetes Targets", href: "/control-plane/kubernetes", body: "rpi_kubernetes deployment status, logs, restart, and Terraform deploy controls." },
  { title: "Identity + SCIM", href: "/control-plane/identity", body: "Auth0 status, SCIM provisioning state, and tenancy sync signals." },
  { title: "Deployments", href: "/control-plane/deployments", body: "Service topology and deployment health across API, workers, MCP, and frontend." },
];

export function ControlPlaneRoute() {
  return (
    <PageContainer
      title="Control Plane"
      subtitle="Authenticated operations for AQP identity, Kubernetes deployment, and service topology."
    >
      <div className="grid gap-3 md:grid-cols-3">
        {CARDS.map((card) => (
          <Link key={card.href} to={card.href}>
            <Card className="h-full hover:border-[var(--info-border)]">
              <CardHeader>
                <CardTitle>{card.title}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-[var(--text-secondary)]">
                {card.body}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </PageContainer>
  );
}
