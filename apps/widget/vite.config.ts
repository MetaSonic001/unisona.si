import { defineConfig } from "vite";

// Builds a single self-contained IIFE script: apps/widget/dist/widget.js (served by the API at /widget/widget.js).
export default defineConfig({
  build: {
    lib: { entry: "src/main.ts", name: "UnisonaWidget", formats: ["iife"], fileName: () => "widget.js" },
    outDir: "dist",
    emptyOutDir: false,
    minify: true,
    target: "es2019",
  },
});
