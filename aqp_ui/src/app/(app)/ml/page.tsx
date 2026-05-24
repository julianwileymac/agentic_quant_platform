import { Card } from "antd";

export const dynamic = "force-dynamic";

export default function MlPage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          ML
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Predictor Hub, AlphaBacktestExperiment, walk-forward training,
          finetune trainers.
        </p>
      </header>
      <Card>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Models register through <code>aqp_models</code>. Use the workbench to
          run flows or compose your own with <code>register("Name", kind="model")</code>.
        </p>
      </Card>
    </div>
  );
}
