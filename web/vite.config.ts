import { resolve } from "node:path";
import { defineConfig } from "vite";

// two pages: the map explorer (index.html) and the OCP1 side-by-side replay (replay.html)
export default defineConfig({
  build: {
    rollupOptions: {
      input: { main: resolve(__dirname, "index.html"), replay: resolve(__dirname, "replay.html") },
    },
  },
});
