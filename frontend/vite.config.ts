import { fileURLToPath, URL } from "node:url";

import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Tutto ciò che inizia per /yf_ è API backend (FastAPI)
      "/yf_": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
      // Le immagini articoli sono servite da Apache (in dev: backend statico)
      "/images": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    target: "es2022",
    rollupOptions: {
      output: {
        manualChunks: {
          // Vendor chunk per cache aggressiva
          vue: ["vue", "vue-router", "pinia"],
          ui: ["@headlessui/vue", "@heroicons/vue"],
          fingerprint: ["@fingerprintjs/fingerprintjs"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
