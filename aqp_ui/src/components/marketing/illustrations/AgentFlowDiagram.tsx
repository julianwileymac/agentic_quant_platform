"use client";

import { motion } from "framer-motion";

/**
 * 3-node sequential/debate flow:
 *
 *   Researcher  --->  Strategist  --->  Trader
 *        |                 |               |
 *        +-------- DataMCP boundary --------+
 *                  (kill-switch top-right)
 *
 * Used in the homepage breakdown and on /product/agentops.
 */
export function AgentFlowDiagram({ className }: { className?: string }) {
  const nodeFade = {
    hidden: { opacity: 0, scale: 0.92 },
    show: (i: number) => ({
      opacity: 1,
      scale: 1,
      transition: { delay: 0.15 * i, duration: 0.5, ease: "easeOut" as const },
    }),
  };

  return (
    <div className={className}>
      <motion.svg
        viewBox="0 0 480 320"
        className="h-auto w-full"
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-50px" }}
        role="img"
        aria-label="Agent flow: Researcher to Strategist to Trader, bounded by the DataMCP layer with a kill-switch overlay and the agent_runs_v2 ledger row below."
      >
        <title>
          Agent flow: Researcher → Strategist → Trader inside the DataMCP boundary
        </title>
        <defs>
          <linearGradient id="agent-node-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#1677ff" stopOpacity={0.18} />
            <stop offset="100%" stopColor="#722ed1" stopOpacity={0.06} />
          </linearGradient>
          <linearGradient id="agent-edge-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#60a5fa" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
          <filter id="agent-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="6" />
            <feMerge>
              <feMergeNode />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Decorative dotted enclosure for DataMCP boundary */}
        <motion.rect
          x={20}
          y={40}
          width={440}
          height={240}
          rx={20}
          fill="none"
          stroke="#334155"
          strokeWidth={1}
          strokeDasharray="4 4"
          variants={{
            hidden: { opacity: 0 },
            show: { opacity: 0.6, transition: { duration: 0.6 } },
          }}
        />
        <motion.text
          x={32}
          y={62}
          fontSize={10}
          fontWeight={600}
          fill="#64748b"
          letterSpacing={1}
          variants={{
            hidden: { opacity: 0 },
            show: { opacity: 1, transition: { delay: 0.2, duration: 0.4 } },
          }}
        >
          DATAMCP BOUNDARY
        </motion.text>

        {/* Top-right kill-switch badge */}
        <motion.g
          variants={{
            hidden: { opacity: 0, x: 8 },
            show: {
              opacity: 1,
              x: 0,
              transition: { delay: 0.4, duration: 0.4 },
            },
          }}
        >
          <rect
            x={356}
            y={50}
            width={92}
            height={22}
            rx={11}
            fill="rgba(239,68,68,0.15)"
            stroke="rgba(239,68,68,0.5)"
            strokeWidth={1}
          />
          <circle cx={370} cy={61} r={3} fill="#ef4444">
            <animate
              attributeName="opacity"
              values="0.4;1;0.4"
              dur="2s"
              repeatCount="indefinite"
            />
          </circle>
          <text
            x={380}
            y={65}
            fontSize={10}
            fontWeight={700}
            fill="#ef4444"
            letterSpacing={0.5}
          >
            KILL-SWITCH
          </text>
        </motion.g>

        {/* Three agent nodes */}
        {[
          { x: 60, label: "Researcher", sub: "AlphaResearcher" },
          { x: 200, label: "Strategist", sub: "StrategyExecutor" },
          { x: 340, label: "Trader", sub: "TraderAgent" },
        ].map((node, i) => (
          <motion.g key={node.label} custom={i + 1} variants={nodeFade}>
            <rect
              x={node.x}
              y={130}
              width={100}
              height={70}
              rx={10}
              fill="url(#agent-node-grad)"
              stroke="rgba(96,165,250,0.5)"
              strokeWidth={1.5}
              filter="url(#agent-glow)"
            />
            <circle
              cx={node.x + 50}
              cy={155}
              r={10}
              fill="#1677ff"
              opacity={0.9}
            />
            <text
              x={node.x + 50}
              y={159}
              fontSize={10}
              textAnchor="middle"
              fill="white"
              fontWeight={700}
            >
              {i + 1}
            </text>
            <text
              x={node.x + 50}
              y={180}
              fontSize={12}
              textAnchor="middle"
              fill="#e5e7eb"
              fontWeight={600}
            >
              {node.label}
            </text>
            <text
              x={node.x + 50}
              y={194}
              fontSize={9}
              textAnchor="middle"
              fill="#64748b"
            >
              {node.sub}
            </text>
          </motion.g>
        ))}

        {/* Flow arrows between nodes */}
        {[
          { from: 160, to: 200 },
          { from: 300, to: 340 },
        ].map((edge) => (
          <motion.g
            key={`edge-${edge.from}`}
            variants={{
              hidden: { opacity: 0 },
              show: {
                opacity: 1,
                transition: { delay: 0.55, duration: 0.5 },
              },
            }}
          >
            <line
              x1={edge.from}
              y1={165}
              x2={edge.to - 6}
              y2={165}
              stroke="url(#agent-edge-grad)"
              strokeWidth={2}
              className="animate-flow-line"
            />
            <polygon
              points={`${edge.to - 6},161 ${edge.to},165 ${edge.to - 6},169`}
              fill="#a78bfa"
            />
          </motion.g>
        ))}

        {/* Bottom ledger row */}
        <motion.g
          variants={{
            hidden: { opacity: 0, y: 8 },
            show: {
              opacity: 1,
              y: 0,
              transition: { delay: 0.75, duration: 0.5 },
            },
          }}
        >
          <rect
            x={60}
            y={232}
            width={380}
            height={32}
            rx={8}
            fill="rgba(15,23,42,0.5)"
            stroke="#334155"
            strokeWidth={1}
          />
          <text
            x={72}
            y={252}
            fontSize={10}
            fill="#64748b"
            fontWeight={600}
            letterSpacing={0.5}
          >
            agent_runs_v2
          </text>
          {[120, 180, 240, 300, 360, 420].map((cx, i) => (
            <circle
              key={cx}
              cx={cx}
              cy={248}
              r={3}
              fill={i % 2 === 0 ? "#10b981" : "#1677ff"}
              opacity={0.8}
            />
          ))}
        </motion.g>
      </motion.svg>
    </div>
  );
}
