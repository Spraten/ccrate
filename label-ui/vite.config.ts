import { resolve } from 'node:path'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  base: './',
  plugins: [vue(), tailwindcss()],
  resolve: { alias: { '@print-design-pro': resolve(__dirname, 'vendor/print-design-pro/src') } },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: { input: { editor: resolve(__dirname, 'editor.html'), render: resolve(__dirname, 'render.html') } },
  },
})
