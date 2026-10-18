/** Capture popup screenshots of reward search for a set of queries. */
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const here = path.dirname(fileURLToPath(import.meta.url));
const extensionDir = path.resolve(here, '../.output/chrome-mv3');
const outDir = process.env.LAPSE_SCREENSHOT_DIR ?? '/opt/cursor/artifacts/screenshots';
const chromePath = process.env.CHROME_PATH ?? '/usr/bin/google-chrome';
const queries = process.argv.slice(2);
if (queries.length === 0) queries.push('mexican food', 'streetwear', 'food', 'clothing');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

await mkdir(outDir, { recursive: true });
// Branded Chrome 137+ removed --load-extension; install via the DevTools pipe.
const browser = await puppeteer.launch({
  executablePath: chromePath,
  headless: false,
  pipe: true,
  enableExtensions: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

try {
  const extensionId = await browser.installExtension(extensionDir);
  const page = await browser.newPage();
  await page.setViewport({ width: 380, height: 640, deviceScaleFactor: 2 });
  await page.goto(`chrome-extension://${extensionId}/popup.html`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('[data-testid="search-input"]', { timeout: 15000 });
  await sleep(500);

  for (const query of queries) {
    await page.evaluate(() => {
      const input = document.querySelector('[data-testid="search-input"]');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(input, '');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await page.type('[data-testid="search-input"]', query, { delay: 20 });
    await page.waitForSelector('[data-testid="search-result"], [data-testid="search-empty"]', {
      timeout: 10000,
    });
    await sleep(400);
    const file = path.join(outDir, `search-${query.replace(/\s+/g, '-')}.png`);
    await page.screenshot({ path: file, fullPage: true });
    const count = await page.$$eval('[data-testid="search-result"]', (nodes) => nodes.length);
    const first = await page
      .$eval('[data-testid="search-result"]', (node) => node.innerText.replace(/\n/g, ' | '))
      .catch(() => '(none)');
    console.log(`${query}: ${count} results -> ${file}\n  top: ${first}`);
  }
} finally {
  await browser.close();
}
