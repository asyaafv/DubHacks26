/**
 * Demo capture for "use it before you lose it":
 * 1. Sends HCOWINTER25 through the merchant console (instant mode).
 * 2. Visits a fake hollisterco.com cart page -> screenshots the Lapse Sense toast.
 * 3. Opens the popup, runs the $500 stack -> screenshots the recommendation.
 */
import { createServer } from 'node:http';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const API_BASE = process.env.LAPSE_API_BASE ?? 'http://localhost:8000';
const DEMO_USER = '00000000-0000-0000-0000-000000000001';
const here = path.dirname(fileURLToPath(import.meta.url));
const extensionDir = path.resolve(here, '../.output/chrome-mv3');
const outDir = process.env.LAPSE_SCREENSHOT_DIR ?? '/opt/cursor/artifacts/screenshots';
const chromePath = process.env.CHROME_PATH ?? '/usr/bin/google-chrome';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function api(route, init = {}) {
  const response = await fetch(`${API_BASE}${route}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', 'X-User-Id': DEMO_USER, ...(init.headers ?? {}) },
  });
  if (!response.ok) throw new Error(`${route} -> ${response.status}: ${await response.text()}`);
  return response.json();
}

async function main() {
  await mkdir(outDir, { recursive: true });

  const health = await api('/health');
  if (health.status !== 'healthy') throw new Error('Backend not healthy');

  // Send HCOWINTER25 exactly like the merchant console demo does.
  const sent = await api('/demo/console/send', {
    method: 'POST',
    body: JSON.stringify({
      template_id: 'hollister_10',
      overrides: { value: 25, code: 'HCOWINTER25', expiry_days: 30 },
      mode: 'instant',
      user_id: DEMO_USER,
      force: true,
    }),
  });
  const codes = (sent.rewards ?? []).map((r) => r.code);
  console.log('console send extracted:', codes.join(', ') || '(nothing)');
  if (!codes.includes('HCOWINTER25')) throw new Error('HCOWINTER25 was not extracted');

  // Sanity: lookup must now rank HCOFALL10 first with the use-first flag.
  const lookup = await api('/lookup', {
    method: 'POST',
    body: JSON.stringify({ user_id: DEMO_USER, domain: 'hollisterco.com', limit: 10 }),
  });
  console.log('lookup order:', lookup.rewards.map((s) =>
    `${s.reward.code}${s.use_first ? ' [USE FIRST]' : ''}${s.save_for_later ? ' [LATER]' : ''}`).join(' | '));
  if (!lookup.rewards[0]?.use_first || lookup.rewards[0].reward.code !== 'HCOFALL10') {
    throw new Error('Lookup did not rank HCOFALL10 as use-first');
  }

  const server = createServer((_req, res) => {
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    res.end('<!doctype html><title>Shopping Bag | Hollister</title><body style="font-family:sans-serif;background:#fafafa"><h1>Shopping Bag</h1><p>Subtotal: $500.00 · Checkout</p></body>');
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: false,
    pipe: true,
    enableExtensions: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--host-resolver-rules=MAP hollisterco.com 127.0.0.1'],
  });

  try {
    await browser.installExtension(extensionDir);
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 2 });
    await page.goto(`http://hollisterco.com:${port}/cart`, { waitUntil: 'domcontentloaded' });

    // The Lapse Sense hero toast is injected by the content script
    // (closed shadow DOM, so wait on the host element only).
    await page.waitForSelector('[data-testid="lapse-sense-toast"]', { timeout: 25000 });
    await sleep(1800); // let the slide-in animation settle
    await page.screenshot({ path: path.join(outDir, 'use-first-toast.png') });
    console.log('toast screenshot saved');

    const workerTarget = await browser.waitForTarget((t) => t.type() === 'service_worker', { timeout: 15000 });
    const extensionId = new URL(workerTarget.url()).host;
    const popup = await browser.newPage();
    await popup.setViewport({ width: 400, height: 900, deviceScaleFactor: 2 });
    await popup.goto(`chrome-extension://${extensionId}/popup.html`, { waitUntil: 'networkidle0' });
    await popup.waitForSelector('[data-testid="reward-code"]', { timeout: 15000 });
    await popup.waitForFunction(
      () => document.body.innerText.toLowerCase().includes('hollister'),
      { timeout: 15000 },
    );

    // Run the $500 cart stack (fixture scenario).
    const cartInput = await popup.$('[data-testid="cart-total"]');
    if (cartInput) {
      await cartInput.click({ clickCount: 3 });
      await popup.type('[data-testid="cart-total"]', '500');
      await popup.click('[data-testid="stack-button"]');
      await popup.waitForSelector('[data-testid="total-savings"]', { timeout: 15000 }).catch(() => {});
      await sleep(600);
    }
    await popup.screenshot({ path: path.join(outDir, 'use-first-popup.png'), fullPage: true });
    console.log('popup screenshot saved; mentions:', await popup.evaluate(() => {
      const text = document.body.innerText.toLowerCase();
      return {
        useFirst: text.includes('use first'),
        saveForLater: text.includes('save for later'),
        winter: text.includes('hcowinter25'),
      };
    }));
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
