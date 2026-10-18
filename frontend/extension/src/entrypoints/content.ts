import { detectFromUrl } from '../core/page';

export default defineContentScript({
  matches: ['*://*/*'],
  runAt: 'document_idle',
  main(ctx) {
    let lastKey = '';

    const report = () => {
      const page = detectFromUrl(window.location.href, document.title);
      if (!page) return;
      const key = `${page.domain}|${page.isCheckout}|${page.url}`;
      if (key === lastKey) return;
      lastKey = key;
      void browser.runtime.sendMessage({ type: 'PAGE_VISIT', ...page }).catch(() => {
        // The service worker may be restarting. The next navigation or popup open retries.
      });
    };

    report();
    ctx.addEventListener(window, 'popstate', report);
    ctx.addEventListener(window, 'hashchange', report);
    ctx.setInterval(report, 1500);
  },
});
