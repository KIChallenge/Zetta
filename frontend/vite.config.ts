import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// The backend has no /api prefix, so its paths are proxied one by one to keep the browser same-origin.
const api = process.env.API_PROXY_TARGET ?? 'http://localhost:8000'
const proxy = { '/auth/': api, '^/me(/|$)': api, '^/chats(/|$)': api }

// Only our own scripts, styles, fonts and API. Vite injects <style> tags, hence 'unsafe-inline' for styles only.
// Whatever serves the built app in production must send these headers too.
const csp = (dev: boolean) =>
  [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src 'self'${dev ? ' ws: wss:' : ''}`, // hot reload
    `frame-ancestors ${dev ? "'self'" : "'none'"}`, // the Vue devtools panel is a same-origin frame
    "base-uri 'none'",
    "form-action 'self'",
    "object-src 'none'",
  ].join('; ')
const headers = (dev: boolean) => ({
  'Content-Security-Policy': csp(dev),
  'X-Frame-Options': dev ? 'SAMEORIGIN' : 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
})

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    headers: headers(true),
    proxy,
  },
  preview: {
    headers: headers(false),
    proxy,
  },
})
