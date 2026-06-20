import { defineConfig, devices } from '@playwright/test'

// E2E regression tests run against an already-running stack (the Docker
// container on :80, or `npm run dev` on :5173). Point at either via env:
//   E2E_BASE_URL=http://localhost npx playwright test        # docker (default)
//   E2E_BASE_URL=http://localhost:5173 npx playwright test   # vite dev
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost'

export default defineConfig({
  testDir: './e2e',
  // A 500-deal DDS solve takes several seconds; give each test generous room.
  timeout: 120_000,
  expect: { timeout: 90_000 },
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
