import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // In development the FastAPI service runs on :8000; in production it serves this app itself.
  server: {
    proxy: { '/api': 'http://localhost:8000', '/healthz': 'http://localhost:8000' },
  },
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/firebase') || id.includes('node_modules/@firebase')) return 'firebase';
          if (id.includes('node_modules/recharts') || id.includes('node_modules/d3-')) return 'charts';
          return undefined;
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    css: false,
    coverage: {
      provider: 'v8',
      include: ['src/**'],
      exclude: ['src/test/**', 'src/main.jsx'],
      thresholds: { statements: 85, branches: 70, functions: 80, lines: 90 },
    },
  },
});
