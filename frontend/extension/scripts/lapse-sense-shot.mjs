/**
 * Screenshot the Direction B extension surfaces against a live backend:
 *  1. the on-page Lapse Sense toast on a matched store page (Hollister cart)
 *  2. the popup on that cart showing the best stack for a $500 total
 * Uses the DevTools-pipe installExtension path (branded Chrome 137+ removed
 * --load-extension), same as search-screenshots.mjs.
 */
import { createServer } from 'node:http';
import { mkdir, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const here = path.dirname(fileURLToPath(import.meta.url));
const extensionDir = path.resolve(here, '../.output/chrome-mv3');
const outDir = process.env.LAPSE_SCREENSHOT_DIR ?? '/opt/cursor/artifacts/screenshots';
const chromePath = process.env.CHROME_PATH ?? '/usr/bin/google-chrome';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const output = await readdir(extensionDir);
if (!output.includes('manifest.json')) throw new Error('Build the extension first');
await mkdir(outDir, { recursive: true });

const server = createServer((_req, res) => {
  res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
  res.end(`<!doctype html><title>Shopping Bag | Hollister</title>
<body style="margin:0;font-family:system-ui;background:#fff">
<div style="border-bottom:1px solid #ddd;padding:18px 32px;font-weight:700;font-size:20px;letter-spacing:0.2em">HOLLISTER</div>
<div style="padding:32px;max-width:820px">
<h1 style="font-size:24px">Shopping Bag (4 items)</h1>
<div style="display:flex;gap:16px;border:1px solid #eee;padding:16px;margin-top:16px"><div style="width:72px;height:90px;background:#eee"></div><div><b>Signature Hoodie</b><div>Qty 2 · $89.95</div></div></div>
<div style="display:flex;gap:16px;border:1px solid #eee;padding:16px;margin-top:8px"><div style="width:72px;height:90px;background:#eee"></div><div><b>Athletic Joggers</b><div>Qty 2 · $69.95</div></div></div>
<div style="margin-top:24px;font-size:18px"><b>Subtotal: $500.00</b></div>
</div></body>`);
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const { port } = server.address();

const browser = await puppeteer.launch({
  executablePath: chromePath,
  headless: false,
  pipe: true,
  enableExtensions: true,
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--host-resolver-rules=MAP hollisterco.com 127.0.0.1',
  ],
});

try {
  const extensionId = await browser.installExtension(extensionDir);

  // 1) Store page → content script → background /lookup → Lapse Sense toast.
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 2 });
  await page.goto(`http://hollisterco.com:${port}/cart`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="lapse-sense-toast"]', { timeout: 20000 });
  await sleep(700); // slide-in animation
  await page.screenshot({ path: path.join(outDir, 'lapse_sense_toast_hollister.png') });
  console.log('OK lapse_sense_toast_hollister.png');

  // 2) Popup on that cart: rewards, then the best stack for $500.
  const popup = await browser.newPage();
  await popup.setViewport({ width: 400, height: 760, deviceScaleFactor: 2 });
  await popup.goto(`chrome-extension://${extensionId}/popup.html`, { waitUntil: 'networkidle0' });
  await popup.waitForSelector('[data-testid="store-name"]', { timeout: 15000 });
  await popup.click('[data-testid="cart-total"]', { clickCount: 3 });
  await popup.type('[data-testid="cart-total"]', '500');
  await popup.click('[data-testid="stack-button"]');
  await popup.waitForSelector('[data-testid="final-price"]', { timeout: 15000 });
  await sleep(400);
  const summary = await popup.evaluate(() => ({
    store: document.querySelector('[data-testid="store-name"]')?.textContent ?? '',
    final: document.querySelector('[data-testid="final-price"]')?.textContent ?? '',
    savings: document.querySelector('[data-testid="total-savings"]')?.textContent ?? '',
    card: document.querySelector('[data-testid="recommended-card"]')?.textContent ?? '',
  }));
  console.log('popup state', JSON.stringify(summary));
  if (!summary.final.includes('$450.00')) throw new Error(`Final price was ${summary.final}`);
  await popup.screenshot({ path: path.join(outDir, 'popup_hollister_stack_b.png'), fullPage: true });
  console.log('OK popup_hollister_stack_b.png');
} finally {
  await browser.close();
  server.close();
}
