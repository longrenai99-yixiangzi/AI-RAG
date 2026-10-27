import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: { __LOCAL_PLATFORM__: 'true' },
  build: { rollupOptions: { input: { index: 'index.html', platform: 'platform.html' } } },
})
