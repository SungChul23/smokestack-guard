import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import devData from "./dev-data-plugin.mjs";

// 빌드 결과물 이름에 해시가 붙는다(Vite 기본) → CloudFront에서 1년 캐시, index.html만 no-cache
export default defineConfig({
  plugins: [react(), devData()],
  server: { port: 5173 },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: { modules: { classNameStrategy: "non-scoped" } },
  },
});
