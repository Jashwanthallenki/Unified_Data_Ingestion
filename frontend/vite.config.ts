import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, base = "/" and the proxy hits Django at :8000.
// In prod build, base = "/static/" so Django + WhiteNoise serve the bundle from STATIC_URL.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/static/" : "/",
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    emptyOutDir: true,
  },
}));
