/** Screenshot the on-page Lapse Sense toast on a matched store (Hollister cart). */
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
  headless: true,
  ignoreDefaultArgs: ['--disable-extensions'],
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    `--disable-extensions-except=${extensionDir}`,
    `--load-extension=${extensionDir}`,
    '--host-resolver-rules=MAP hollisterco.com 127.0.0.1',
  ],
});

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 2 });
  await page.goto(`http://hollisterco.com:${port}/cart`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="lapse-sense-toast"]', { timeout: 20000 });
  await sleep(900); // slide-in animation
  await page.screenshot({ path: path.join(outDir, 'lapse_sense_toast_hollister.png') });
  console.log('OK lapse_sense_toast_hollister.png');
} finally {
  await browser.close();
  server.close();
}
