import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The site is deployed as a GitHub Pages "project page" at
// https://<owner>.github.io/SCFMarvel/  → base must match the repo name.
// For local dev / other hosts, set VITE_BASE=/ (or override as needed).
const base = process.env.VITE_BASE ?? "/SCFMarvel/";

export default defineConfig({
  base,
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
