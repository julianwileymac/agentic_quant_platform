"use client";

import { motion } from "framer-motion";

/**
 * Stacked tenancy strategy illustration:
 *   RLS shared schema (top)
 *   Schema-per-tenant (middle)
 *   Database-per-enterprise (bottom)
 */
export function MultiTenantIllustration({ className }: { className?: string }) {
  const strategies = [
    {
      title: "Shared schema + RLS",
      sub: "Most B2C tiers",
      color: "#60a5fa",
      y: 60,
      tenants: 3,
    },
    {
      title: "Schema-per-tenant",
      sub: "Team tier isolation",
      color: "#34d399",
      y: 170,
      tenants: 3,
    },
    {
      title: "Database-per-enterprise",
      sub: "Enterprise tier",
      color: "#a78bfa",
      y: 280,
      tenants: 2,
    },
  ];

  return (
    <div className={className}>
      <motion.svg
        viewBox="0 0 480 380"
        className="h-auto w-full"
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-50px" }}
      >
        {strategies.map((s, i) => (
          <motion.g
            key={s.title}
            variants={{
              hidden: { opacity: 0, x: 12 },
              show: {
                opacity: 1,
                x: 0,
                transition: { delay: 0.1 + i * 0.15, duration: 0.5 },
              },
            }}
          >
            {/* Strategy outer container */}
            <rect
              x={30}
              y={s.y}
              width={420}
              height={80}
              rx={10}
              fill={`${s.color}11`}
              stroke={`${s.color}66`}
              strokeWidth={1}
              strokeDasharray={i === 0 ? undefined : "3 3"}
            />
            <text
              x={42}
              y={s.y + 22}
              fontSize={12}
              fill={s.color}
              fontWeight={700}
            >
              {s.title}
            </text>
            <text x={42} y={s.y + 38} fontSize={10} fill="#94a3b8">
              {s.sub}
            </text>

            {/* Tenant rectangles inside */}
            {Array.from({ length: s.tenants }).map((_, ti) => {
              const slot = 100 / s.tenants;
              const x = 42 + (ti * (380 - 16)) / s.tenants;
              const w = (380 - 16) / s.tenants - 8;
              return (
                <g key={`${s.title}-tenant-${slot}-${x}`}>
                  <rect
                    x={x}
                    y={s.y + 48}
                    width={w}
                    height={26}
                    rx={4}
                    fill={`${s.color}22`}
                    stroke={`${s.color}aa`}
                    strokeWidth={1}
                  />
                  <text
                    x={x + w / 2}
                    y={s.y + 65}
                    fontSize={10}
                    fill="#e5e7eb"
                    fontWeight={600}
                    textAnchor="middle"
                  >
                    tenant_{ti + 1}
                  </text>
                </g>
              );
            })}
          </motion.g>
        ))}
        {/* RLS row indicator dots */}
        <motion.g
          variants={{
            hidden: { opacity: 0 },
            show: { opacity: 1, transition: { delay: 0.8, duration: 0.5 } },
          }}
        >
          <text
            x={240}
            y={362}
            fontSize={10}
            textAnchor="middle"
            fill="#64748b"
            fontWeight={600}
            letterSpacing={1}
          >
            TENANCYSTRATEGY · ROW-LEVEL SECURITY · ENVELOPE-ENCRYPTED BYOK
          </text>
        </motion.g>
      </motion.svg>
    </div>
  );
}
