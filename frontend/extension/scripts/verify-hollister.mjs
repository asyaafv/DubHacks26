import { createServer } from 'node:http';
import { mkdir, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

async function findChrome() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'chrome');
  try {
    const versions = await readdir(root);
    for (const version of versions) {
      const candidate = path.join(root, version, 'chrome-linux64', 'chrome');
      try {
        await readdir(path.dirname(candidate));
        return candidate;
      } catch {
        // try the next downloaded build
      }
    }
  } catch {
    // Chrome for Testing is optional; fall back to the system binary.
  }
  return '/usr/bin/google-chrome';
}

const here = path.dirname(fileURLToPath(import.meta.url));
const extensionDir = path.resolve(here, '../.output/chrome-mv3');
const screenshotPath =
  process.env.LAPSE_SCREENSHOT ?? '/opt/cursor/artifacts/hollister_cart_stack.png';

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function listen() {
  const server = createServer((_req, res) => {
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    res.end('<!doctype html><title>Shopping Bag | Hollister</title><h1>Shopping Bag</h1>');
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('No port');
  return { server, port: address.port };
}

async function extensionWorker(browser) {
  const target = await browser.waitForTarget(
    (candidate) => candidate.type() === 'service_worker' && candidate.url().includes('chrome-extension://'),
    { timeout: 20000 },
  );
  const worker = await target.worker();
  if (!worker) throw new Error('Extension service worker has no target');
  return { worker, id: new URL(target.url()).host };
}

async function waitForHollister(worker) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const state = await worker.evaluate(async () => {
      const stored = await chrome.storage.local.get(['currentDomain', 'isCheckout', 'currentLookup']);
      const badge = await chrome.action.getBadgeText({});
      return { ...stored, badge };
    });
    const code = state.currentLookup?.rewards?.[0]?.reward?.code;
    if (state.currentDomain === 'hollisterco.com' && state.isCheckout && code === 'HCOFALL10') {
      return state;
    }
    await sleep(250);
  }
  const debug = await worker.evaluate(() => chrome.storage.local.get(null));
  throw new Error(`Content script did not report the Hollister cart: ${JSON.stringify(debug)}`);
}

async function main() {
  const output = await readdir(extensionDir);
  if (!output.includes('manifest.json')) {
    throw new Error(`Build the extension first. Missing ${extensionDir}/manifest.json`);
  }

  const { server, port } = await listen();
  const executablePath = await findChrome();
  console.log('chrome', executablePath);
  const browser = await puppeteer.launch({
    executablePath,
    headless: process.env.LAPSE_HEADED === '1' ? false : true,
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
    const { worker, id } = await extensionWorker(browser);
    const page = await browser.newPage();
    const cartUrl = `http://hollisterco.com:${port}/cart`;
    await page.goto(cartUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
    const state = await waitForHollister(worker);
    if (state.badge !== '1') {
      throw new Error(`Expected badge 1, got ${JSON.stringify(state.badge)}`);
    }

    const popup = await browser.newPage();
    await popup.setViewport({ width: 400, height: 720, deviceScaleFactor: 1 });
    await popup.goto(`chrome-extension://${id}/popup.html`, { waitUntil: 'networkidle0' });
    await popup.waitForSelector('[data-testid="reward-code"]', { timeout: 10000 });

    const before = await popup.evaluate(() => ({
      store: document.querySelector('[data-testid="store-name"]')?.textContent ?? '',
      code: document.querySelector('[data-testid="reward-code"]')?.textContent ?? '',
      value: document.querySelector('[data-testid="reward-value"]')?.textContent ?? '',
      expiry: document.querySelector('[data-testid="expiry"]')?.textContent ?? '',
      expiryColor: getComputedStyle(document.querySelector('[data-testid="expiry"]')).color,
      checkout: document.querySelector('[data-testid="checkout-pill"]')?.textContent ?? '',
    }));

    if (!before.store.includes('Hollister')) throw new Error(`Store was ${before.store}`);
    if (!before.code.includes('HCOFALL10')) throw new Error(`Code was ${before.code}`);
    if (!before.value.includes('10%')) throw new Error(`Value was ${before.value}`);
    if (before.expiry !== 'Expires in 2 days') throw new Error(`Expiry was ${before.expiry}`);
    if (!before.checkout.includes('Cart')) throw new Error('Cart pill missing');
    const [red, green] = before.expiryColor.match(/\d+/g)?.map(Number) ?? [];
    if (!(red > green)) throw new Error(`Expiry was not red: ${before.expiryColor}`);

    await popup.click('[data-testid="reward-code"]');
    await popup.waitForFunction(
      () => document.querySelector('[data-testid="reward-code"]')?.textContent?.includes('Copied'),
      { timeout: 3000 },
    );

    await popup.click('[data-testid="cart-total"]', { clickCount: 3 });
    await popup.type('[data-testid="cart-total"]', '500');
    await popup.click('[data-testid="stack-button"]');
    await popup.waitForSelector('[data-testid="total-savings"]', { timeout: 10000 });

    const after = await popup.evaluate(() => ({
      finalPrice: document.querySelector('[data-testid="final-price"]')?.textContent ?? '',
      savings: document.querySelector('[data-testid="total-savings"]')?.textContent ?? '',
      card: document.querySelector('[data-testid="recommended-card"]')?.textContent ?? '',
      explanation: document.querySelector('[data-testid="explanation"]')?.textContent ?? '',
      stackCode: document.querySelector('[data-testid="stack-code"]')?.textContent ?? '',
      toast: document.querySelector('[data-testid="toast"]')?.textContent ?? '',
      dashboard: document.querySelector('[data-testid="open-dashboard"]')?.textContent ?? '',
    }));

    if (!after.finalPrice.includes('$450.00')) throw new Error(`Final price was ${after.finalPrice}`);
    if (!after.savings.includes('$72.50')) throw new Error(`Savings were ${after.savings}`);
    if (!after.card.includes('Cash+')) throw new Error(`Card was ${after.card}`);
    if (!after.explanation.includes('HCOFALL10')) throw new Error(`Explanation was ${after.explanation}`);
    if (!after.stackCode.includes('HCOFALL10')) throw new Error(`Stack code was ${after.stackCode}`);
    if (!after.toast.includes('reward_added') && !after.toast.toLowerCase().includes('new reward')) {
      throw new Error(`Toast was ${after.toast}`);
    }
    if (!after.dashboard.includes('Open dashboard')) throw new Error('Dashboard button missing');

    await mkdir(path.dirname(screenshotPath), { recursive: true });
    await popup.screenshot({ path: screenshotPath, fullPage: true });
    console.log(
      JSON.stringify(
        {
          cartUrl,
          extensionId: id,
          badge: state.badge,
          before,
          after,
          screenshot: screenshotPath,
        },
        null,
        2,
      ),
    );
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
