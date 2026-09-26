/// <reference types="vitest/config" />
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Tests pin the locale (Intl reads it once at process start, so it must be set before Vitest forks its workers):
// results must not depend on the machine's LC_ALL / LANG / TZ (a French laptop must pass like CI).
if (process.env.VITEST) {
  process.env.LC_ALL = "en_US.UTF-8";
  process.env.LANG = "en_US.UTF-8";
  process.env.TZ = "UTC";
}

// The build goes straight into the Python package so `careeros ui` serves it with no Node at runtime.
// The output is committed; CI rebuilds and fails if it differs (see .github/workflows/tests.yml).
const outDir = fileURLToPath(new URL("../src/careeros/ui/static", import.meta.url));

export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir,
    emptyOutDir: true,
    sourcemap: false,
    reportCompressedSize: false,
  },
  server: {
    port: 5173,
    // `careeros ui` on its default port serves the API during development.
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    pool: "forks",
  },
});
