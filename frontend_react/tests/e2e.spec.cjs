// AEGIS React SPA end-to-end — runs against the backend that serves the built
// SPA + /verify on one port. BASE defaults to http://localhost:8000.
const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:8000';

test.describe('Purchaser', () => {
  test('clean → Made in Canada, verified, all four categories pass', async ({ page }) => {
    await page.goto(`${BASE}/purchaser`);
    await page.getByTestId('sample-clean').click();
    await expect(page.getByTestId('report')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('designation')).toHaveText('Made in Canada');
    await expect(page.getByTestId('pct')).toContainText('58.4');
    await expect(page.getByTestId('chain-valid')).toContainText('VERIFIED');
    for (const k of ['integrity', 'structure', 'mass_balance', 'statistical'])
      await expect(page.getByTestId(`cat-${k}-status`)).toContainText('PASS');
  });
  test('tampered → chain invalid, integrity category fails', async ({ page }) => {
    await page.goto(`${BASE}/purchaser`);
    await page.getByTestId('sample-tampered').click();
    await expect(page.getByTestId('chain-valid')).toContainText('INVALID', { timeout: 10000 });
    await expect(page.getByTestId('cat-integrity-status')).toContainText('FAIL');
    await expect(page.getByTestId('cat-integrity')).toContainText('signature_invalid');
    await expect(page.getByTestId('cat-structure-status')).toContainText('PASS');
  });
  test('offshore → Not Qualified', async ({ page }) => {
    await page.goto(`${BASE}/purchaser`);
    await page.getByTestId('sample-foreign').click();
    await expect(page.getByTestId('designation')).toHaveText('Not Qualified', { timeout: 10000 });
  });
});

// enterprise 2-step login: pick a demo identity, then enter the shown 2FA code
async function loginDemo(page) {
  await page.goto(`${BASE}/supplier`);
  await page.getByTestId('demo-login').first().click();
  await expect(page.getByTestId('otp')).toBeVisible({ timeout: 10000 });
  const code = (await page.getByTestId('demo-otp').innerText()).trim();
  const boxes = page.locator('[data-testid=otp] input');
  for (let i = 0; i < 6; i++) await boxes.nth(i).fill(code[i]);
  await expect(page.getByText('key verified')).toBeVisible({ timeout: 10000 });
}

test.describe('Supplier wallet', () => {
  test('2FA login → load drone parts → sign final assembly → Made in Canada', async ({ page }) => {
    await loginDemo(page);
    await page.getByTestId('new-submission').click();
    await page.getByTestId('seed-parts').click();
    await page.getByRole('button', { name: 'Sign attestation' }).click();
    await expect(page.getByTestId('last-att-id')).toBeVisible({ timeout: 10000 });
    await page.getByTestId('verify-this').click();
    await expect(page.getByTestId('designation')).toHaveText('Made in Canada', { timeout: 10000 });
    await expect(page.getByTestId('chain-valid')).toContainText('VERIFIED');
  });

  test('lone raw material → Not Qualified with explanation (no spurious violation)', async ({ page }) => {
    await loginDemo(page);
    await page.getByTestId('new-submission').click();
    await page.getByRole('button', { name: 'Sign attestation' }).click();
    await expect(page.getByTestId('last-att-id')).toBeVisible({ timeout: 10000 });
    await page.getByTestId('verify-this').click();
    await expect(page.getByTestId('designation')).toHaveText('Not Qualified', { timeout: 10000 });
    await expect(page.getByTestId('why')).toContainText('substantial transformation');
    await expect(page.getByTestId('chain-valid')).toContainText('VERIFIED');
  });
  test('publish → QR → purchaser resolves by product id', async ({ page }) => {
    await loginDemo(page);
    await page.getByTestId('new-submission').click();
    await page.getByTestId('seed-parts').click();
    await page.getByRole('button', { name: 'Sign attestation' }).click();
    await page.getByTestId('verify-this').click();
    await expect(page.getByTestId('designation')).toHaveText('Made in Canada', { timeout: 10000 });
    await page.getByTestId('publish').click();
    await expect(page.getByTestId('qr-img')).toBeVisible({ timeout: 10000 });
    const pid = (await page.locator('[data-testid=qr-block] .mono').innerText()).trim();
    // purchaser resolves the published product (as if the QR was scanned)
    await page.goto(`${BASE}/purchaser?pid=${pid}`);
    await expect(page.getByTestId('designation')).toHaveText('Made in Canada', { timeout: 10000 });
    await expect(page.getByTestId('chain-valid')).toContainText('VERIFIED');
  });

  test('bad key rejected at credentials step', async ({ page }) => {
    await page.goto(`${BASE}/supplier`);
    await page.locator('input').first().fill('sup-avss-corp');
    await page.locator('input').nth(1).fill('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=');
    await page.getByRole('button', { name: 'Continue →' }).click();
    await expect(page.getByTestId('login-error')).toContainText('does not match', { timeout: 10000 });
  });

  test('wrong 2FA code rejected', async ({ page }) => {
    await page.goto(`${BASE}/supplier`);
    await page.getByTestId('demo-login').first().click();
    await expect(page.getByTestId('otp')).toBeVisible({ timeout: 10000 });
    const boxes = page.locator('[data-testid=otp] input');
    for (let i = 0; i < 6; i++) await boxes.nth(i).fill('0');  // 000000, won't match
    await page.getByTestId('verify-2fa').click();
    await expect(page.getByTestId('login-error')).toContainText('Incorrect authentication code', { timeout: 10000 });
  });
});
