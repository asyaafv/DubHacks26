/**
 * Screenshot the Lapse Sense hero toast against a live backend:
 *  1. Hollister cart (subtotal on page → full card with stack preview)
 *  2. Domino's menu page (no cart total → compact card without stack row)
 * Uses the DevTools-pipe installExtension path (branded Chrome 137+ removed
 * --load-extension), same as search-screenshots.mjs.
 */
import { execSync } from 'node:child_process';
import { createServer } from 'node:https';
import { existsSync, readFileSync } from 'node:fs';
import { mkdir, readdir } from 'node:fs/promises';
import os from 'node:os';
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

const PAGES = {
  'hollisterco.com': `<!doctype html><title>Shopping Bag | Hollister</title>
<body style="margin:0;font-family:system-ui;background:#fff">
<div style="border-bottom:1px solid #ddd;padding:18px 32px;font-weight:700;font-size:20px;letter-spacing:0.2em">HOLLISTER</div>
<div style="padding:32px;max-width:820px">
<h1 style="font-size:24px">Shopping Bag (4 items)</h1>
<div style="display:flex;gap:16px;border:1px solid #eee;padding:16px;margin-top:16px"><div style="width:72px;height:90px;background:#eee"></div><div><b>Signature Hoodie</b><div>Qty 2 · $89.95</div></div></div>
<div style="display:flex;gap:16px;border:1px solid #eee;padding:16px;margin-top:8px"><div style="width:72px;height:90px;background:#eee"></div><div><b>Athletic Joggers</b><div>Qty 2 · $69.95</div></div></div>
<div style="margin-top:24px;font-size:18px"><b>Subtotal: $500.00</b></div>
</div></body>`,
  'dominos.com': `<!doctype html><title>Menu | Domino's Pizza</title>
<body style="margin:0;font-family:system-ui;background:#fff">
<div style="border-bottom:1px solid #ddd;padding:18px 32px;font-weight:700;font-size:20px;color:#0A6EB4">Domino's <span style="color:#E31837">Pizza</span></div>
<div style="padding:32px;max-width:820px">
<h1 style="font-size:24px">Build your order</h1>
<div style="display:flex;gap:16px;border:1px solid #eee;padding:16px;margin-top:16px"><div style="width:72px;height:72px;border-radius:50%;background:#eee"></div><div><b>Large Pepperoni Pizza</b><div>Hand Tossed · $14.99</div></div></div>
<div style="display:flex;gap:16px;border:1px solid #eee;padding:16px;margin-top:8px"><div style="width:72px;height:72px;border-radius:50%;background:#eee"></div><div><b>Cheesy Bread</b><div>8-piece · $7.99</div></div></div>
</div></body>`,
};

// HTTPS with a throwaway self-signed cert: HSTS-preloaded domains (e.g.
// starbucks.com) refuse plain http, and Chrome runs with
// --ignore-certificate-errors below.
const certDir = path.join(os.tmpdir(), 'lapse-sense-cert');
const keyFile = path.join(certDir, 'key.pem');
const certFile = path.join(certDir, 'cert.pem');
if (!existsSync(certFile)) {
  await mkdir(certDir, { recursive: true });
  execSync(
    `openssl req -x509 -newkey rsa:2048 -nodes -keyout ${keyFile} -out ${certFile} -days 2 -subj "/CN=lapse-demo"`,
    { stdio: 'ignore' },
  );
}

const server = createServer({ key: readFileSync(keyFile), cert: readFileSync(certFile) }, (req, res) => {
  const hostname = (req.headers.host ?? '').split(':')[0].replace(/^www\./, '');
  res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
  res.end(PAGES[hostname] ?? PAGES['hollisterco.com']);
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
    '--ignore-certificate-errors',
    '--host-resolver-rules=MAP hollisterco.com 127.0.0.1, MAP dominos.com 127.0.0.1',
  ],
});

try {
  await browser.installExtension(extensionDir);

  const shots = [
    { url: `https://hollisterco.com:${port}/cart`, file: 'lapse_sense_hero_hollister.png' },
    { url: `https://dominos.com:${port}/menu`, file: 'lapse_sense_hero_dominos.png' },
  ];
  for (const shot of shots) {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 2 });
    await page.goto(shot.url, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="lapse-sense-toast"]', { timeout: 20000 });
    await sleep(900); // slide-in + stack fetch
    await page.screenshot({ path: path.join(outDir, shot.file) });
    console.log('OK', shot.file);
    await page.close();
  }
} finally {
  await browser.close();
  server.close();
}
