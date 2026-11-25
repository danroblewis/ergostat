import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built into ../static/app and served by ergostat's own server at / and each page's path (web/server.py). `npm run dev`
// serves the same app at http://localhost:5173 and proxies the API to a running ergostat (ERGOSTAT_URL, default
// http://127.0.0.1:8781). UI_OUT builds somewhere else (a check build that must not touch the served copy).
const target = process.env.ERGOSTAT_URL || "http://127.0.0.1:8781";
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/static/app/" : "/",
  plugins: [react()],
  build: { outDir: process.env.UI_OUT || "../static/app", emptyOutDir: true, chunkSizeWarningLimit: 4000 },
  server: { proxy: { "/api": target, "/file": target } },
}));
