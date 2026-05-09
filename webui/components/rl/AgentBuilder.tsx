"use client";

import { App, Button, Card, Form, Input, InputNumber, Select, Space, Typography } from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";

const { Text } = Typography;

const FRAMEWORKS = [
  { value: "SB3Adapter", label: "SB3 (PPO / SAC / TD3 / DDPG / DQN / sb3-contrib)" },
  { value: "ElegantRLAdapter", label: "ElegantRL (PPO / SAC / TD3 / DDPG / DQN)" },
  { value: "RayRLlibAdapter", label: "Ray RLlib (distributed)" },
  { value: "CleanRLAdapter", label: "CleanRL (single-file PPO)" },
  { value: "LLMHybridAgent", label: "LLM-hybrid (FinRobot bridge)" },
];

const SB3_ALGOS = ["PPO", "A2C", "DDPG", "SAC", "TD3", "DQN", "RecurrentPPO", "TRPO", "QRDQN", "MaskablePPO"];
const ELEGANTRL_ALGOS = ["PPO", "A2C", "DDPG", "SAC", "TD3", "DQN"];
const RLLIB_ALGOS = ["PPO", "A2C", "A3C", "DDPG", "SAC", "TD3", "DQN", "IMPALA", "APEX-DQN"];
const CLEANRL_ALGOS = ["PPO"];

export function AgentBuilder() {
  const { message } = App.useApp();
  const [framework, setFramework] = useState<string>("SB3Adapter");
  const [algorithm, setAlgorithm] = useState<string>("PPO");
  const [policy, setPolicy] = useState<string>("MlpPolicy");
  const [learningRate, setLearningRate] = useState<number>(3e-4);
  const [llmModel, setLlmModel] = useState<string>("");
  const [llmWeight, setLlmWeight] = useState<number>(0.5);

  function algoOptions(): string[] {
    if (framework === "ElegantRLAdapter") return ELEGANTRL_ALGOS;
    if (framework === "RayRLlibAdapter") return RLLIB_ALGOS;
    if (framework === "CleanRLAdapter") return CLEANRL_ALGOS;
    if (framework === "LLMHybridAgent") return ["LLMHybrid"];
    return SB3_ALGOS;
  }

  function buildSpec() {
    if (framework === "LLMHybridAgent") {
      return {
        class: "LLMHybridAgent",
        module_path: "aqp.rl.agents.llm_hybrid",
        kwargs: {
          rl_agent: {
            class: "SB3Adapter",
            module_path: "aqp.rl.agents.sb3_adapter",
            kwargs: { algorithm, policy, learning_rate: learningRate },
          },
          llm_model: llmModel,
          llm_weight: llmWeight,
        },
      };
    }
    return {
      class: framework,
      module_path: `aqp.rl.agents.${
        framework === "SB3Adapter"
          ? "sb3_adapter"
          : framework === "ElegantRLAdapter"
            ? "elegantrl_adapter"
            : framework === "RayRLlibAdapter"
              ? "rllib_adapter"
              : "cleanrl_adapter"
      }`,
      kwargs: {
        algorithm,
        ...(framework === "SB3Adapter" || framework === "RayRLlibAdapter"
          ? { policy }
          : {}),
        learning_rate: learningRate,
      },
    };
  }

  function copyToClipboard() {
    const json = JSON.stringify(buildSpec(), null, 2);
    void navigator.clipboard.writeText(json);
    message.success("Agent spec copied to clipboard");
  }

  return (
    <PageContainer
      title="Agent builder"
      subtitle="Pick a framework + algorithm + hyperparams. The resulting spec plugs into RLExperimentSpec.agent."
    >
      <Card size="small">
        <Form layout="vertical" style={{ maxWidth: 720 }}>
          <Form.Item label="Framework">
            <Select
              value={framework}
              onChange={(v) => {
                setFramework(v);
                const allowed = algoOptions();
                if (!allowed.includes(algorithm)) {
                  setAlgorithm(allowed[0] ?? "PPO");
                }
              }}
              options={FRAMEWORKS}
            />
          </Form.Item>
          <Form.Item label="Algorithm">
            <Select
              value={algorithm}
              onChange={setAlgorithm}
              options={algoOptions().map((a) => ({ value: a, label: a }))}
            />
          </Form.Item>
          <Form.Item label="Policy network (SB3 / RLlib only)">
            <Input value={policy} onChange={(e) => setPolicy(e.target.value)} placeholder="MlpPolicy" />
          </Form.Item>
          <Form.Item label="Learning rate">
            <InputNumber
              value={learningRate}
              onChange={(v) => setLearningRate(Number(v) || 3e-4)}
              step={1e-5}
              style={{ width: "100%" }}
            />
          </Form.Item>
          {framework === "LLMHybridAgent" ? (
            <>
              <Form.Item label="LLM model alias (router_complete)">
                <Input
                  value={llmModel}
                  onChange={(e) => setLlmModel(e.target.value)}
                  placeholder="nemotron-3-nano:30b"
                />
              </Form.Item>
              <Form.Item label="LLM blend weight (0-1)">
                <InputNumber
                  min={0}
                  max={1}
                  step={0.05}
                  value={llmWeight}
                  onChange={(v) => setLlmWeight(Number(v) || 0)}
                  style={{ width: "100%" }}
                />
              </Form.Item>
            </>
          ) : null}
          <Space>
            <Button type="primary" onClick={copyToClipboard}>
              Copy JSON
            </Button>
          </Space>
          <Card size="small" title="Resulting spec" style={{ marginTop: 16 }}>
            <pre style={{ margin: 0, fontSize: 12 }}>{JSON.stringify(buildSpec(), null, 2)}</pre>
          </Card>
        </Form>
      </Card>
    </PageContainer>
  );
}
