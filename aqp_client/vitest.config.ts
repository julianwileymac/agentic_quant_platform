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
  },
});
