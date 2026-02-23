import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Vite root is editor/ — build output goes to editor/dist/
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      // Forward all /api/* requests to the Python server during development
      '/api': {
        target: 'http://localhost:7421',
        changeOrigin: true,
      },
    },
  },
});
