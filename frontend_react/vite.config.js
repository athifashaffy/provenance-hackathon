import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Build to ../backend/static so FastAPI serves the SPA from one container/port.
// Dev server proxies /verify and /api to the backend on :8000.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/verify': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
});
