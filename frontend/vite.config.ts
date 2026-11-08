import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API runs separately, so dev proxies /api to it rather than the console embedding a base URL.
// Section 21.1's rule has a corollary here: the frontend holds no knowledge of where a figure comes
// from beyond the path it asks for, which is why there is no client-side cache or derived store.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: { outDir: "dist", sourcemap: true },
});
