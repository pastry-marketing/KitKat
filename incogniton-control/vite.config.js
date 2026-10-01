import { defineConfig } from "vite";
import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: "public",
  plugins: [{
    name: "kitkat-bridge-download",
    apply: "build",
    async closeBundle() {
      const outputDir = path.join(projectRoot, "dist", "downloads");
      await mkdir(outputDir, { recursive: true });
      await copyFile(
        path.join(projectRoot, "public", "downloads", "KitKat-Bridge.zip"),
        path.join(outputDir, "KitKat-Bridge.zip")
      );
    }
  }],
  build: {
    outDir: "../dist",
    emptyOutDir: true
  }
});
