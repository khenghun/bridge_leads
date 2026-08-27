import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

/** Emit the built `play.html` as `index.html`.
 *
 * The play image serves the bundle from nginx's document root exactly like the
 * lead image does (`try_files ... /index.html`), so the entry has to land under
 * that name. Renaming at the bundle level — rather than keeping a second
 * `index.html` in the source tree — leaves one unambiguous entry file per
 * product in the repo. */
function emitAsIndexHtml(): Plugin {
  return {
    name: 'play-html-as-index',
    enforce: 'post',
    generateBundle(_options, bundle) {
      const page = bundle['play.html']
      if (!page) return
      delete bundle['play.html']
      page.fileName = 'index.html'
      bundle['index.html'] = page
    },
  }
}

/** Where `/api` goes in dev.
 *
 * The play solver is its own FastAPI app in its own container, so locally it
 * runs BESIDE the lead API rather than instead of it:
 *   backend/ $ ../.venv/Scripts/uvicorn app_play.main:app --reload --port 8001
 * In production nginx.play.conf proxies /api to the play container on 8000 —
 * this constant only ever applies to the Vite dev server. */
const DEV_API = 'http://localhost:8001'

// Same shape as vite.config.ts: the browser stays same-origin in dev (no CORS),
// and in production nginx serves the built assets and proxies /api itself.
export default defineConfig({
  // Own dep-cache: the lead and play dev servers run side by side from one
  // node_modules, and two Vite configs sharing `node_modules/.vite` keep
  // re-optimising and invalidating each other's pre-bundled React ("504
  // Outdated Optimize Dep", blank page).
  cacheDir: 'node_modules/.vite-play',
  plugins: [react(), emitAsIndexHtml()],
  build: {
    rollupOptions: {
      input: 'play.html',
    },
  },
  server: {
    proxy: {
      '/api': DEV_API,
    },
  },
})
