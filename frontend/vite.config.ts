import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: { '/api/v1': 'http://127.0.0.1:8787' } },
  test: { environment: 'jsdom', setupFiles: ['./tests/setup.ts'], include: ['tests/unit/**/*.test.ts?(x)'] },
});
