import { createServer } from 'node:http';
import { mkdir, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const API_BASE = process.env.LAPSE_API_BASE ?? 'http://localhost:8000';
const DEMO_USER = '00000000-0000-0000-0000-000000000001';

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
const screenshotDir = process.env.LAPSE_SCREENSHOT_DIR ?? '/opt/cursor/artifacts/screenshots';

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function api(route, init = {}) {
  const response = await fetch(`${API_BASE}${route}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', 'X-User-Id': DEMO_USER, ...(init.headers ?? {}) },
  });
  if (!response.ok) throw new Error(`${route} -> ${response.status}`);
  return response.json();
}

async function backendIsLive() {
  try {
    const health = await api('/health');
    return health?.status === 'healthy';
  } catch {
    return false;
  }
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

async function waitForToast(worker) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const stored = await worker.evaluate(() => chrome.storage.local.get(['toasts']));
    const toasts = stored.toasts ?? [];
    const hit = toasts.find((toast) => toast.message?.includes('New reward'));
    if (hit) return hit;
    await sleep(500);
  }
  throw new Error('No reward_added toast arrived from /events');
}

async function snap(page, name) {
  await mkdir(screenshotDir, { recursive: true });
  const file = path.join(screenshotDir, name);
  await page.screenshot({ path: file, fullPage: true });
  console.log('screenshot', file);
  return file;
}

async function main() {
  const output = await readdir(extensionDir);
  if (!output.includes('manifest.json')) {
    throw new Error(`Build the extension first. Missing ${extensionDir}/manifest.json`);
  }

  const live = await backendIsLive();
  console.log(live ? `live backend at ${API_BASE}` : 'no backend — verifying mock fallback path');

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
      ...(process.env.LAPSE_HEADED === '1' ? ['--window-size=1280,800'] : []),
    ],
  });

  try {
    const { worker, id } = await extensionWorker(browser);

    let savingsBefore = null;
    let toast = null;
    if (live) {
      savingsBefore = Number((await api('/savings')).total);
      console.log('savings before:', savingsBefore.toFixed(2));
      // Give the service worker a beat to open the SSE stream, then "send" the
      // merchant email exactly like the demo console's instant mode does.
      await sleep(2000);
      const inject = await api('/demo/inject', {
        method: 'POST',
        body: JSON.stringify({
          eml_filename: 'hollister_10_percent.eml',
          user_id: DEMO_USER,
          force: true,
        }),
      });
      if (inject.rewards_extracted < 1) throw new Error(`Inject extracted nothing: ${JSON.stringify(inject)}`);
      console.log('injected email, rewards_extracted =', inject.rewards_extracted);
      toast = await waitForToast(worker);
      console.log('toast:', toast.message);
      if (!toast.message.includes('Hollister')) throw new Error(`Toast missing merchant: ${toast.message}`);
    }

    const page = await browser.newPage();
    const cartUrl = `http://hollisterco.com:${port}/cart`;
    await page.goto(cartUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
    const state = await waitForHollister(worker);
    if (live) {
      if (!(Number(state.badge) >= 1)) throw new Error(`Expected badge >= 1, got ${JSON.stringify(state.badge)}`);
    } else if (state.badge !== '1') {
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
      toast: document.querySelector('[data-testid="toast"]')?.textContent ?? '',
    }));

    if (!before.store.includes('Hollister')) throw new Error(`Store was ${before.store}`);
    if (!before.code.includes('HCOFALL10')) throw new Error(`Code was ${before.code}`);
    if (!before.value.includes('10%')) throw new Error(`Value was ${before.value}`);
    if (!/Expires (today|in \d+ days?)/.test(before.expiry)) throw new Error(`Expiry was ${before.expiry}`);
    if (!before.checkout.includes('Cart')) throw new Error('Cart pill missing');
    const [red, green] = before.expiryColor.match(/\d+/g)?.map(Number) ?? [];
    if (!(red > green)) throw new Error(`Expiry was not red: ${before.expiryColor}`);
    if (live && !before.toast.includes('New reward')) throw new Error(`Popup toast missing: ${before.toast}`);
    await snap(popup, 'popup_hollister_rewards.png');

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
    await snap(popup, 'popup_stack_result.png');

    // Copy the stack code, then mark the reward used and confirm savings grew.
    await popup.click('[data-testid="stack-code"]');
    let savingsAfter = null;
    if (live) {
      await popup.click('[data-testid="mark-used"]');
      await popup.waitForFunction(
        () => document.querySelector('[data-testid="mark-used"]')?.textContent === 'Used',
        { timeout: 10000 },
      );
      savingsAfter = Number((await api('/savings')).total);
      console.log('savings after:', savingsAfter.toFixed(2));
      if (!(savingsAfter > savingsBefore + 49.99)) {
        throw new Error(`Savings did not grow by the $50 reward: ${savingsBefore} -> ${savingsAfter}`);
      }
      await snap(popup, 'popup_marked_used.png');
    }

    console.log(
      JSON.stringify(
        {
          mode: live ? 'live' : 'mock-fallback',
          cartUrl,
          extensionId: id,
          badge: state.badge,
          toast: toast?.message ?? null,
          before,
          after,
          savingsBefore,
          savingsAfter,
        },
        null,
        2,
      ),
    );
    if (process.env.LAPSE_HOLD_MS) await sleep(Number(process.env.LAPSE_HOLD_MS));
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
