import { test, expect } from '@playwright/test'

// End-to-end regression smoke test. Drives the real UI against a running stack
// (frontend -> nginx -> FastAPI -> DDS), so it also proves the container wiring
// (libgomp1 / DDS load, /api proxy) — not just the React layer.
//
// Assertions are deliberately STRUCTURAL, not numeric: we check the flow works
// and the results are well-formed, so ordinary engine tuning won't break the
// test. Add a numeric-golden test separately if a specific output ever needs
// locking down.
//
// A fixed leader hand keeps the run deterministic (the engine seeds with 0).
const HAND = 'T.KT932.Q2.T9843'

test.describe('opening-lead simulator', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Opening Lead Simulator' })).toBeVisible()
  })

  test('runs a simulation and ranks candidate leads', async ({ page }) => {
    // Default contract is 3NT by South -> West (LHO) is on lead.
    await expect(page.getByText('Opening leader: West')).toBeVisible()

    // Enter the hand via the PBN paste box (deterministic vs. Random hand).
    await page.getByRole('textbox', { name: /Paste PBN/ }).fill(HAND)
    await expect(page.getByText('13/13 cards entered')).toBeVisible()

    const simulate = page.getByRole('button', { name: 'Simulate' })
    await expect(simulate).toBeEnabled()
    await simulate.click()

    // Recommendation banner appears (IMP mode is the default).
    const banner = page.locator('.banner-success')
    await expect(banner).toBeVisible()
    await expect(banner).toContainText(/Recommended lead/)
    await expect(banner).toContainText('IMPs')
    await expect(banner).toContainText(/defeats \d+%/)

    // One ranked row per card in the 13-card hand (results table is first).
    const resultRows = page.locator('table.results tbody tr')
    await expect(resultRows).toHaveCount(13)
    // At least one lead is highlighted as the recommendation.
    await expect(page.locator('table.results tbody tr.row-best').first()).toBeVisible()

    // Sample deals render for the recommended lead.
    await expect(page.getByRole('heading', { name: 'Sample deals' })).toBeVisible()
  })

  test('scoring toggle re-ranks client-side without re-running', async ({ page }) => {
    await page.getByRole('textbox', { name: /Paste PBN/ }).fill(HAND)
    await page.getByRole('button', { name: 'Simulate' }).click()

    const banner = page.locator('.banner-success')
    await expect(banner).toContainText('IMPs')

    // Switching to Matchpoints re-ranks the SAME response client-side: the
    // banner metric flips to MP% with no network round-trip / spinner.
    await page.getByRole('button', { name: 'Matchpoints' }).click()
    await expect(banner).toContainText('MP%')
    await expect(banner).not.toContainText('IMPs')
    // Table is still populated (13 leads) after the re-rank.
    await expect(page.locator('table.results tbody tr')).toHaveCount(13)
  })
})
