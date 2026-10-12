/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  // Tests (npm test) run with Vitest in jsdom, a simulated browser.
  test: {
    environment: 'jsdom',
    // A fixed API address (with a trailing slash), so tests don't depend on your .env.
    env: { VITE_API_URL: 'http://api.test/' },
  },
});
