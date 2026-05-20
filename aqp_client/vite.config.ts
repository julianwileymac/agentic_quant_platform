import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_URL ?? "http://localhost:8000";
  const wsTarget = env.VITE_WS_URL ?? apiTarget.replace(/^http/, "ws");

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 3001,
      strictPort: true,
      proxy: {
        "/aqp-api": {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/aqp-api/, ""),
        },
        "/aqp-ws": {
          target: wsTarget,
          ws: true,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/aqp-ws/, ""),
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: true,
    },
  };
});
