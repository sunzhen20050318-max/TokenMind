import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const tokenMindApiTarget = process.env.TOKENMIND_API_PROXY || 'http://localhost:18888'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: tokenMindApiTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: tokenMindApiTarget.replace(/^http/, 'ws'),
        ws: true,
        configure: (proxy) => {
          proxy.on('error', (err) => {
            const code = (err as { code?: string }).code
            if (code === 'EPIPE' || code === 'ECONNRESET') return
            console.error('[ws proxy]', err)
          })
        },
      },
    },
  },
})
