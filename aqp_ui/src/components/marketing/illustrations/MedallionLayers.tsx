"use client";

import { motion } from "framer-motion";

/**
 * Bronze -> Silver -> Gold three-cylinder medallion lakehouse illustration.
 */
export function MedallionLayers({ className }: { className?: string }) {
  const layers = [
    {
      label: "Bronze",
      sub: "aqp_bronze_*",
      detail: "Raw ingest",
      color: "#cd7f32",
      lighter: "#e8b07a",
      y: 250,
    },
    {
      label: "Silver",
      sub: "aqp_silver_*",
      detail: "Normalised",
      color: "#b8b8b8",
      lighter: "#dcdcdc",
      y: 160,
    },
    {
      label: "Gold",
      sub: "aqp_gold_*",
      detail: "Products",
      color: "#ffd700",
      lighter: "#ffe680",
      y: 70,
    },
  ];

  return (
    <div className={className}>
      <motion.svg
        viewBox="0 0 480 360"
        className="h-auto w-full"
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-50px" }}
        role="img"
        aria-label="Medallion lakehouse layers: Bronze raw, Silver normalised, Gold products — stacked cylinders with promotion arrows."
      >
        <title>Medallion lakehouse: Bronze → Silver → Gold</title>
        {/* Faint Iceberg "lake" base */}
        <ellipse
          cx={240}
          cy={345}
          rx={200}
          ry={10}
          fill="#1e293b"
          opacity={0.5}
        />

        {layers.map((layer, i) => (
          <motion.g
            key={layer.label}
            variants={{
              hidden: { opacity: 0, y: 16 },
              show: {
                opacity: 1,
                y: 0,
                transition: { delay: 0.1 + i * 0.15, duration: 0.5 },
              },
            }}
          >
            {/* Cylinder body */}
            <rect
              x={140}
              y={layer.y + 14}
              width={200}
              height={50}
              fill={layer.color}
              opacity={0.18}
            />
            <rect
              x={140}
              y={layer.y + 14}
              width={200}
              height={50}
              fill="none"
              stroke={layer.color}
              strokeWidth={1.5}
              opacity={0.85}
            />
            {/* Top ellipse */}
            <ellipse
              cx={240}
              cy={layer.y + 14}
              rx={100}
              ry={14}
              fill={layer.lighter}
              opacity={0.25}
            />
            <ellipse
              cx={240}
              cy={layer.y + 14}
              rx={100}
              ry={14}
              fill="none"
              stroke={layer.color}
              strokeWidth={1.5}
            />
            {/* Bottom ellipse (shows through) */}
            <path
              d={`M 140 ${layer.y + 64} A 100 14 0 0 0 340 ${layer.y + 64}`}
              fill="none"
              stroke={layer.color}
              strokeWidth={1.5}
              opacity={0.85}
            />
            {/* Label */}
            <text
              x={240}
              y={layer.y + 42}
              fontSize={16}
              textAnchor="middle"
              fill={layer.color}
              fontWeight={700}
            >
              {layer.label}
            </text>
            <text
              x={240}
              y={layer.y + 56}
              fontSize={10}
              textAnchor="middle"
              fill="#94a3b8"
              fontFamily="monospace"
            >
              {layer.sub}
            </text>
            {/* Right-hand explainer */}
            <text
              x={356}
              y={layer.y + 36}
              fontSize={11}
              fill="#e5e7eb"
              fontWeight={600}
            >
              {layer.detail}
            </text>
          </motion.g>
        ))}

        {/* Promotion arrows */}
        {[
          { y1: 226, y2: 174 },
          { y1: 136, y2: 84 },
        ].map((arrow) => (
          <motion.g
            key={`arrow-${arrow.y1}`}
            variants={{
              hidden: { opacity: 0 },
              show: {
                opacity: 1,
                transition: { delay: 0.6, duration: 0.5 },
              },
            }}
          >
            <line
              x1={110}
              y1={arrow.y1}
              x2={110}
              y2={arrow.y2 + 6}
              stroke="#60a5fa"
              strokeWidth={2}
              className="animate-flow-line"
            />
            <polygon
              points={`106,${arrow.y2 + 6} 110,${arrow.y2} 114,${arrow.y2 + 6}`}
              fill="#60a5fa"
            />
          </motion.g>
        ))}

        {/* Footer */}
        <motion.text
          x={240}
          y={342}
          fontSize={11}
          textAnchor="middle"
          fill="#64748b"
          fontWeight={600}
          letterSpacing={1}
          variants={{
            hidden: { opacity: 0 },
            show: { opacity: 1, transition: { delay: 0.8, duration: 0.5 } },
          }}
        >
          ICEBERG · APPEND_ARROW · BUSINESSMETADATA
        </motion.text>
      </motion.svg>
    </div>
  );
}
