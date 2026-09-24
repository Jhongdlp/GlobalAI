import { defineConfig } from "astro/config";

export default defineConfig({
  devToolbar: { enabled: false },
  vite: {
    // Mismo origen que la API en local: la cookie httpOnly viaja sin CORS ni SameSite=None.
    server: { proxy: { "/api": "http://localhost:8000" } },
  },
});
