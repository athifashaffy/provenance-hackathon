// AEGIS UI end-to-end: supplier wallet login + sign + verify, purchaser verdicts.
// Run against the live stack: FRONTEND defaults to http://localhost:3001.
const { test, expect } = require('@playwright/test');

const FRONTEND = process.env.FRONTEND_URL || 'http://localhost:3001';

test.describe('Purchaser — /verify verdicts', () => {
  test('clean product → Made in Canada, chain verified, 0 anomalies', async ({ page }) => {
    await page.goto(`${FRONTEND}/purchaser.html`);
    await page.getByTestId('sample-clean').click();
    const report = page.getByTestId('report');
    await expect(report).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('designation')).toHaveText('Made in Canada');
    await expect(page.getByTestId('pct')).toContainText('58.4');
    await expect(page.getByTestId('chain-valid')).toContainText('VERIFIED');
    await expect(page.getByTestId('anomaly')).toHaveCount(0);
  });

  test('tampered product → chain invalid, signature_invalid flagged', async ({ page }) => {
    await page.goto(`${FRONTEND}/purchaser.html`);
    await page.getByTestId('sample-tampered').click();
    await expect(page.getByTestId('report')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('chain-valid')).toContainText('INVALID');
    await expect(page.getByTestId('anomaly').first()).toContainText('signature_invalid');
  });

  test('offshore final assembly → designation Not Qualified', async ({ page }) => {
    await page.goto(`${FRONTEND}/purchaser.html`);
    await page.getByTestId('sample-foreign').click();
    await expect(page.getByTestId('report')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('designation')).toHaveText('Not Qualified');
  });
});

test.describe('Supplier — enterprise wallet', () => {
  test('login with key → sign attestation → verify chain', async ({ page }) => {
    await page.goto(`${FRONTEND}/supplier.html`);
    // one-click demo login (first identity)
    await page.locator('#demo-logins button').first().click();
    await expect(page.locator('#wallet-view')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#identity-bar')).toContainText('key verified');

    // sign a raw material attestation (no parents) — CA, has cost so it's verifiable
    await page.locator('#f-name').fill('Test Carbon Fibre');
    await page.locator('#f-action').selectOption('raw_material_supply');
    await page.locator('#f-country').selectOption('CA');
    await page.locator('#f-mat').fill('500');
    await page.locator('#f-hrs').fill('0');
    await page.locator('#f-lab').fill('0');
    await page.getByText('Sign attestation', { exact: true }).click();
    await expect(page.getByTestId('last-att-id')).toBeVisible({ timeout: 10000 });

    // verify the issued chain through /verify
    await page.getByText('Verify my chain via /verify →').click();
    await expect(page.getByTestId('verdict')).toBeVisible({ timeout: 10000 });
    // a lone raw material: 100% CA cost but no substantial transformation → none, but chain is valid
    await expect(page.getByTestId('verdict')).toContainText('VERIFIED');
  });

  test('rejects a key that does not match the registry', async ({ page }) => {
    await page.goto(`${FRONTEND}/supplier.html`);
    await page.locator('#login-id').fill('sup-avss-corp');
    await page.locator('#login-key').fill('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=');
    await page.getByText('Unlock wallet').click();
    await expect(page.getByTestId('alert')).toContainText('does not match', { timeout: 10000 });
  });
});
