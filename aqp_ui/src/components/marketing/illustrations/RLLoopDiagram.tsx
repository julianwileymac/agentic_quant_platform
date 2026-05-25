"use client";

import { motion } from "framer-motion";

/**
 * Env <-> Policy <-> Reward loop with the FinRL-X f_S/f_A/f_T/f_R weight-centric
 * pipeline labelled along the bottom.
 */
export function RLLoopDiagram({ className }: { className?: string }) {
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
          <linearGradient id="rl-env-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#10b981" stopOpacity={0.18} />
            <stop offset="100%" stopColor="#10b981" stopOpacity={0.04} />
          </linearGradient>
          <linearGradient
            id="rl-policy-grad"
            x1="0%"
            y1="0%"
            x2="100%"
            y2="100%"
          >
            <stop offset="0%" stopColor="#1677ff" stopOpacity={0.2} />
            <stop offset="100%" stopColor="#1677ff" stopOpacity={0.04} />
          </linearGradient>
          <linearGradient
            id="rl-reward-grad"
            x1="0%"
            y1="0%"
            x2="100%"
            y2="100%"
          >
            <stop offset="0%" stopColor="#722ed1" stopOpacity={0.2} />
            <stop offset="100%" stopColor="#722ed1" stopOpacity={0.04} />
          </linearGradient>
        </defs>

        {/* Background loop circle */}
        <motion.circle
          cx={240}
          cy={170}
          r={120}
          fill="none"
          stroke="#334155"
          strokeWidth={1}
          strokeDasharray="3 5"
          variants={{
            hidden: { opacity: 0 },
            show: { opacity: 0.5, transition: { duration: 0.6 } },
          }}
        />
        {/* Animated tracer dot along the loop */}
        <motion.circle r={4} fill="#60a5fa" opacity={0.7}>
          <animateMotion dur="6s" repeatCount="indefinite">
            <mpath xlinkHref="#rl-loop-path" />
          </animateMotion>
        </motion.circle>
        <path
          id="rl-loop-path"
          d="M 240 50 A 120 120 0 1 1 239.99 50"
          fill="none"
          stroke="none"
        />

        {/* Environment node (top) */}
        <motion.g
          variants={{
            hidden: { opacity: 0, scale: 0.9 },
            show: {
              opacity: 1,
              scale: 1,
              transition: { delay: 0.1, duration: 0.5 },
            },
          }}
        >
          <rect
            x={180}
            y={30}
            width={120}
            height={56}
            rx={10}
            fill="url(#rl-env-grad)"
            stroke="rgba(16,185,129,0.6)"
            strokeWidth={1.5}
          />
          <text
            x={240}
            y={56}
            fontSize={13}
            textAnchor="middle"
            fill="#34d399"
            fontWeight={700}
          >
            Environment
          </text>
          <text
            x={240}
            y={72}
            fontSize={10}
            textAnchor="middle"
            fill="#94a3b8"
          >
            FinRL-X env
          </text>
        </motion.g>

        {/* Policy node (bottom-left) */}
        <motion.g
          variants={{
            hidden: { opacity: 0, scale: 0.9 },
            show: {
              opacity: 1,
              scale: 1,
              transition: { delay: 0.25, duration: 0.5 },
            },
          }}
        >
          <rect
            x={70}
            y={240}
            width={120}
            height={56}
            rx={10}
            fill="url(#rl-policy-grad)"
            stroke="rgba(96,165,250,0.6)"
            strokeWidth={1.5}
          />
          <text
            x={130}
            y={266}
            fontSize={13}
            textAnchor="middle"
            fill="#60a5fa"
            fontWeight={700}
          >
            Policy
          </text>
          <text
            x={130}
            y={282}
            fontSize={10}
            textAnchor="middle"
            fill="#94a3b8"
          >
            PPO / SAC / GRPO
          </text>
        </motion.g>

        {/* Reward node (bottom-right) */}
        <motion.g
          variants={{
            hidden: { opacity: 0, scale: 0.9 },
            show: {
              opacity: 1,
              scale: 1,
              transition: { delay: 0.4, duration: 0.5 },
            },
          }}
        >
          <rect
            x={290}
            y={240}
            width={120}
            height={56}
            rx={10}
            fill="url(#rl-reward-grad)"
            stroke="rgba(167,139,250,0.6)"
            strokeWidth={1.5}
          />
          <text
            x={350}
            y={266}
            fontSize={13}
            textAnchor="middle"
            fill="#a78bfa"
            fontWeight={700}
          >
            Reward
          </text>
          <text
            x={350}
            y={282}
            fontSize={10}
            textAnchor="middle"
            fill="#94a3b8"
          >
            Composite terms
          </text>
        </motion.g>

        {/* Loop arrow labels */}
        <motion.g
          variants={{
            hidden: { opacity: 0 },
            show: {
              opacity: 1,
              transition: { delay: 0.55, duration: 0.5 },
            },
          }}
        >
          <text
            x={158}
            y={140}
            fontSize={10}
            fill="#64748b"
            fontWeight={600}
          >
            action
          </text>
          <text
            x={244}
            y={194}
            fontSize={10}
            fill="#64748b"
            fontWeight={600}
            textAnchor="middle"
          >
            r_t
          </text>
          <text
            x={328}
            y={140}
            fontSize={10}
            fill="#64748b"
            fontWeight={600}
          >
            obs / state
          </text>
        </motion.g>

        {/* Weight-centric pipeline strip */}
        <motion.g
          variants={{
            hidden: { opacity: 0, y: 8 },
            show: {
              opacity: 1,
              y: 0,
              transition: { delay: 0.7, duration: 0.5 },
            },
          }}
        >
          <rect
            x={20}
            y={320}
            width={440}
            height={28}
            rx={6}
            fill="rgba(15,23,42,0.6)"
            stroke="#334155"
            strokeWidth={1}
          />
          {[
            { x: 60, label: "f_S", note: "Selector" },
            { x: 160, label: "f_A", note: "Allocator" },
            { x: 260, label: "f_T", note: "Timing" },
            { x: 360, label: "f_R", note: "Risk overlay" },
          ].map((stage, i, arr) => (
            <g key={stage.label}>
              <text
                x={stage.x}
                y={338}
                fontSize={11}
                fontWeight={700}
                fill="#a78bfa"
              >
                {stage.label}
              </text>
              <text x={stage.x + 22} y={338} fontSize={10} fill="#94a3b8">
                {stage.note}
              </text>
              {i < arr.length - 1 ? (
                <text
                  x={stage.x + 80}
                  y={338}
                  fontSize={10}
                  fill="#64748b"
                >
                  →
                </text>
              ) : null}
            </g>
          ))}
        </motion.g>
      </motion.svg>
    </div>
  );
}
