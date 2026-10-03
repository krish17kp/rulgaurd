import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
  },
  resolve: {
    alias: {
      // .pathname (not fileURLToPath) mangles the "New Volume" space in this
      // project's real path (%20 left undecoded) - found running this suite.
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
