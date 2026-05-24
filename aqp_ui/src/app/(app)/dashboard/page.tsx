import { Card, Col, Row, Statistic } from "antd";
import { ArrowDownRight, ArrowUpRight, Activity, Bot, LineChart } from "lucide-react";

import { getSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const session = await getSession();
  const greeting = session?.user?.name ?? session?.user?.email ?? "there";

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Welcome back, {greeting}
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Org: <code>{session?.claims.orgId ?? "—"}</code> · Workspace:{" "}
          <code>{session?.claims.workspaceId ?? "—"}</code>
        </p>
      </header>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Active strategies"
              value={4}
              prefix={<LineChart size={14} />}
              valueStyle={{ color: "var(--text-primary)" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Running paper trades"
              value={2}
              prefix={<Activity size={14} />}
              valueStyle={{ color: "var(--accent-primary)" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Agents this week"
              value={12}
              prefix={<Bot size={14} />}
              valueStyle={{ color: "var(--text-primary)" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Day P&amp;L"
              value={1.84}
              precision={2}
              suffix="%"
              prefix={<ArrowUpRight size={14} />}
              valueStyle={{ color: "var(--pos-fg)" }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title="Recent paper runs">
            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
              Sprint 4 wires a live AG Grid here against{" "}
              <code>GET /paper/runs</code>.
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="Quick actions">
            <ul className="ml-5 list-disc space-y-2 text-sm" style={{ color: "var(--text-secondary)" }}>
              <li>
                <a href="/strategies/new" style={{ color: "var(--accent-primary)" }}>
                  Create a new strategy
                </a>
              </li>
              <li>
                <a href="/settings/brokers" style={{ color: "var(--accent-primary)" }}>
                  Connect a brokerage
                </a>
              </li>
              <li>
                <a href="/docs/getting-started" style={{ color: "var(--accent-primary)" }}>
                  Read the getting started guide
                </a>
              </li>
            </ul>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
