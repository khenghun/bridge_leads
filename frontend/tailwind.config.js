/** @type {import('tailwindcss').Config} */
// Scoped to the play product on purpose: the lead/contract app is plain CSS
// (src/index.css tokens + component classes) and must stay byte-identical when
// Tailwind is present. PostCSS is project-wide, but Tailwind only emits into a
// stylesheet that carries the @tailwind directives — src/apps/play/play.css is
// the only one — and `content` below only scans the play entry's sources.
export default {
  content: [
    './play.html',
    './src/apps/play/**/*.{ts,tsx}',
    './src/play-main.tsx',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
