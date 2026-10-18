// Run by test_browser_fetch_streaming when NODE_BINARY/PLAYWRIGHT_NODE_MODULE are set.
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_NODE_MODULE);

(async () => {
  const [url, user, cursor, replayReward, liveReward] = process.argv.slice(2);
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage();
    page.on('console', message => {
      if (message.text() === 'READY') process.stdout.write('READY\n');
    });
    await page.goto(url + '/browser-test');
    const result = await page.evaluate(async ({user, cursor, liveReward}) => {
      // Browser WebIDL ignores unknown EventSource options, including headers.
      const nativeStatus = await new Promise(resolve => {
        const source = new EventSource('/events', {headers: {'X-User-Id': user}});
        source.onerror = () => { source.close(); resolve('error'); };
      });
      const {connectEvents} = await import('/fetch-events.mjs');
      const control = new AbortController();
      const received = [];
      const timeout = setTimeout(() => control.abort(), 10000);
      try {
        await connectEvents({url: '/events', userId: user, lastEventId: cursor, signal: control.signal,
          apply: async (event, id) => {
            received.push({event, id});
            if (event.event_type === 'sync_complete') console.log('READY');
            if (event.reward_id === liveReward) control.abort();
          }});
      } finally { clearTimeout(timeout); }
      return {nativeStatus, received};
    }, {user, cursor, liveReward});
    assert.equal(result.nativeStatus, 'error');
    assert.deepEqual(result.received.filter(x => x.event.event_type === 'reward_added').map(x => x.event.reward_id),
                     [replayReward, liveReward]);
    assert(result.received.every(x => x.id.startsWith(user + ':')));
    console.log(JSON.stringify({browser: browser.version(), nativeEventSource: 'header option ignored; rejected',
                               fetchStreaming: 'replay and live committed event received', frames: result.received.length}));
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
