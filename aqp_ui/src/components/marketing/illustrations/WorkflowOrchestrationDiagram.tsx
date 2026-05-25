"use client";

import { motion } from "framer-motion";

/**
 * WorkflowRuntime at the center with seven OrchestrationAdapter spokes:
 * graph, crew, debate, fusion, execution, schedule, studio.
 */
export function WorkflowOrchestrationDiagram({
  className,
}: {
  className?: string;
}) {
  const adapters = [
    { label: "graph", angle: -90 },
    { label: "crew", angle: -38 },
    { label: "debate", angle: 14 },
    { label: "fusion", angle: 66 },
    { label: "execution", angle: 118 },
    { label: "schedule", angle: 170 },
    { label: "studio", angle: 222 },
  ];

  const cx = 240;
  const cy = 180;
  const radius = 130;

  return (
    <div className={className}>
      <motion.svg
        viewBox="0 0 480 360"
        className="h-auto w-full"
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-50px" }}
      >
        <defs>
          <radialGradient id="wf-center-grad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#1677ff" stopOpacity={0.5} />
            <stop offset="100%" stopColor="#1677ff" stopOpacity={0.05} />
          </radialGradient>
        </defs>

        {/* Spoke connectors */}
        {adapters.map((a, i) => {
          const rad = (a.angle * Math.PI) / 180;
          const x = cx + Math.cos(rad) * radius;
          const y = cy + Math.sin(rad) * radius;
          return (
            <motion.line
              key={`spoke-${a.label}`}
              x1={cx}
              y1={cy}
              x2={x}
              y2={y}
              stroke="#475569"
              strokeWidth={1}
              strokeDasharray="3 4"
              variants={{
                hidden: { opacity: 0, pathLength: 0 },
                show: {
                  opacity: 0.6,
                  pathLength: 1,
                  transition: { delay: 0.1 + i * 0.05, duration: 0.5 },
                },
              }}
            />
          );
        })}

        {/* Center node */}
        <motion.g
          variants={{
            hidden: { opacity: 0, scale: 0.7 },
            show: {
              opacity: 1,
              scale: 1,
              transition: { delay: 0.05, duration: 0.5 },
            },
          }}
        >
          <circle
            cx={cx}
            cy={cy}
            r={60}
            fill="url(#wf-center-grad)"
            stroke="rgba(96,165,250,0.6)"
            strokeWidth={1.5}
          />
          <circle
            cx={cx}
            cy={cy}
            r={48}
            fill="rgba(15,23,42,0.7)"
            stroke="rgba(96,165,250,0.4)"
            strokeWidth={1}
            className="animate-pulse-glow"
          />
          <text
            x={cx}
            y={cy - 4}
            fontSize={14}
            textAnchor="middle"
            fill="#e5e7eb"
            fontWeight={700}
          >
            Workflow
          </text>
          <text
            x={cx}
            y={cy + 12}
            fontSize={14}
            textAnchor="middle"
            fill="#60a5fa"
            fontWeight={700}
          >
            Runtime
          </text>
        </motion.g>

        {/* Adapter chips */}
        {adapters.map((a, i) => {
          const rad = (a.angle * Math.PI) / 180;
          const x = cx + Math.cos(rad) * radius;
          const y = cy + Math.sin(rad) * radius;
          return (
            <motion.g
              key={`chip-${a.label}`}
              variants={{
                hidden: { opacity: 0, scale: 0.85 },
                show: {
                  opacity: 1,
                  scale: 1,
                  transition: { delay: 0.3 + i * 0.05, duration: 0.4 },
                },
              }}
            >
              <rect
                x={x - 38}
                y={y - 14}
                width={76}
                height={28}
                rx={14}
                fill="rgba(36,48,66,0.85)"
                stroke="rgba(167,139,250,0.5)"
                strokeWidth={1}
              />
              <text
                x={x}
                y={y + 4}
                fontSize={11}
                textAnchor="middle"
                fill="#e5e7eb"
                fontWeight={600}
              >
                {a.label}
              </text>
            </motion.g>
          );
        })}

        {/* Footer */}
        <motion.text
          x={240}
          y={344}
          fontSize={10}
          textAnchor="middle"
          fill="#64748b"
          fontWeight={600}
          letterSpacing={1}
          variants={{
            hidden: { opacity: 0 },
            show: { opacity: 1, transition: { delay: 0.9, duration: 0.4 } },
          }}
        >
          ORCHESTRATIONADAPTERMETA · HASH-LOCKED WORKFLOWSPEC · REPLAYABLE RUNS
        </motion.text>
      </motion.svg>
    </div>
  );
}
