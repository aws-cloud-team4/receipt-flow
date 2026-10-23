import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Local dev: each backend service runs on its own port; in EKS the ingress routes the same paths.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      "/api": "http://localhost:8000",
      "/chat": "http://localhost:8001",
      "/preprocess": "http://localhost:8002",
    },
  },
});
