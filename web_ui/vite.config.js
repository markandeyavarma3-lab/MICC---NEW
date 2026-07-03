import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev: `npm run dev` proxies /api to the Python server (start it first).
// Prod: `npm run build` -> dist/ is served BY the Python server at :8765.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8765',
        changeOrigin: true,
        headers: { Authorization: 'Basic ' + Buffer.from('admin:micc').toString('base64') },
      },
    },
  },
})
