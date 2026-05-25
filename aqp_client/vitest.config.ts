import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/*
 * Vite 7 (declared as a runtime dep via @tailwindcss/vite) conflicts
 * with the older Vite version transitively pinned by Vitest 2 — TS
 * widens the union and complains. We pass the plugins array through
 * an `unknown` cast so the config typechecks without changing runtime
 * behaviour.
 */
const plugins = [react()] as unknown as [];

// Phase 1 §4.4 — frontend test discipline: Vitest coverage threshold
// wired to PR-blocking at a 60% baseline. The threshold ratchets up
// 5%/quarter; each lift is a separate PR that bumps the four numbers
// below in lockstep (lines / statements / functions / branches).
//
// Promotion track:
//   2026 Q3: 60% (this PR)
//   2026 Q4: 65%
//   2027 Q1: 70%
//   2027 Q2: 75%
const COVERAGE_THRESHOLD = 60;

export default defineConfig({
  plugins,
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/unit/**/*.test.{ts,tsx}"],
    setupFiles: ["./tests/unit/setup.ts"],
    coverage: {
      // V8 is the default Node coverage provider — no extra Babel
      // instrumentation required, which keeps test runtimes flat.
      provider: "v8",
      // text + html for local DX, lcov for Codecov / CI consumption.
      reporter: ["text", "html", "lcov"],
      // Only measure source under src/. Tests, fixtures, generated
      // OpenAPI client, build outputs and node_modules are excluded.
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.d.ts",
        "src/lib/api/generated/**",
        "src/main.tsx",
        "src/vite-env.d.ts",
        "src/**/__fixtures__/**",
        "src/**/types.ts",
        "src/**/*.stories.{ts,tsx}",
      ],
      // Enforced thresholds (Phase 1 §4.4). Each is set to the current
      // baseline so a regression below 60% on any axis blocks the PR.
      thresholds: {
        lines: COVERAGE_THRESHOLD,
        statements: COVERAGE_THRESHOLD,
        functions: COVERAGE_THRESHOLD,
        branches: COVERAGE_THRESHOLD,
      },
    },
  },
});
