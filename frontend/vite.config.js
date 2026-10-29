import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

export default defineConfig({
  root: '.',
  plugins: [
    react(),
    tailwindcss()
  ],
  server: {
    port: 3000,
    host: '0.0.0.0',
    open: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/nifty': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/option-chain': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/strategy': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/forecast-vol': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/regime': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/backtest': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true
      }
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  }
});
