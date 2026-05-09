"use client";

import { Card, Tabs, Typography } from "antd";

import { PageContainer } from "@/components/shell/PageContainer";

import { AgentBuilder } from "./AgentBuilder";
import { EnvironmentBuilder } from "./EnvironmentBuilder";
import { ExperimentBuilder } from "./ExperimentBuilder";
import { ObservationBuilder } from "./ObservationBuilder";
import { RewardModelBuilder } from "./RewardModelBuilder";
import { RlComponentLibrary } from "./RlComponentLibrary";

const { Paragraph } = Typography;

/**
 * Single-stop RL Lab — combines the four interactive builders, the
 * component library browser, and a "test" surface for full
 * experiments. Each tab is a stand-alone shell so the same components
 * can be embedded in dedicated routes (e.g. ``/rl/builder/reward``).
 */
export function RlLabPage() {
  return (
    <PageContainer
      title="RL Lab"
      subtitle="Build, preview, and run reinforcement-learning experiments on AQP's data plane."
    >
      <Card size="small" style={{ marginBottom: 12 }}>
        <Paragraph style={{ margin: 0 }}>
          Build environments, reward models, observations, and agents from registered components,
          then save them as <code>RLExperimentSpec</code> blueprints and queue training. Trajectories
          flow into Iceberg through <code>aqp.rl.trajectories.iceberg_writer</code> so every step is
          replayable from the runs view.
        </Paragraph>
      </Card>
      <Tabs
        defaultActiveKey="experiment"
        items={[
          { key: "experiment", label: "Experiment", children: <ExperimentBuilder /> },
          { key: "env", label: "Environment", children: <EnvironmentBuilder /> },
          { key: "reward", label: "Reward", children: <RewardModelBuilder /> },
          { key: "observation", label: "Observation", children: <ObservationBuilder /> },
          { key: "agent", label: "Agent", children: <AgentBuilder /> },
          { key: "library", label: "Component library", children: <RlComponentLibrary /> },
        ]}
      />
    </PageContainer>
  );
}
