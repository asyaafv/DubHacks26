// Chrome extension background script usage. No token/identity in query strings.
// apply(event, id) must finish applying state and checkpointing id before returning.
export async function connectEvents({url, userId, lastEventId = '', apply, signal}) {
  let cursor = lastEventId;
  let retry = 1000;
  const delay = ms => new Promise(resolve => {
    if (signal?.aborted) return resolve();
    const done = () => { clearTimeout(timer); signal?.removeEventListener('abort', done); resolve(); };
    const timer = setTimeout(done, ms);
    signal?.addEventListener('abort', done, {once: true});
  });
  while (!signal?.aborted) {
    let reader;
    let applicationFailed = false;
    try {
      const response = await fetch(url, {
        headers: {'X-User-Id': userId, Accept: 'text/event-stream',
                  ...(cursor ? {'Last-Event-ID': cursor} : {})},
        cache: 'no-store', signal,
      });
      if (!response.ok) {
        if (response.status >= 400 && response.status < 500 && response.status !== 429) {
          throw Object.assign(new Error(`SSE HTTP ${response.status}`), {fatal: true});
        }
        throw new Error(`SSE HTTP ${response.status}`);
      }
      if (!response.headers.get('content-type')?.startsWith('text/event-stream')) {
        throw Object.assign(new Error('Expected an SSE response'), {fatal: true});
      }
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (!signal?.aborted) {
        const {value, done} = await reader.read();
        if (done) break; // An incomplete final frame is replayed after reconnect.
        buffer += decoder.decode(value, {stream: true});
        if (buffer.length > 1024 * 1024) throw new Error('SSE frame too large');
        let boundary;
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          let id = '', type = 'message', data = [];
          for (const line of frame.split('\n')) {
            if (line.startsWith('id: ')) id = line.slice(4);
            else if (line.startsWith('event: ')) type = line.slice(7);
            else if (line.startsWith('data: ')) data.push(line.slice(6));
          }
          if (data.length) {
            // Server uses LF framing and one JSON data line; comments are ignored.
            applicationFailed = true;
            await apply(JSON.parse(data.join('\n')), id, type);
            applicationFailed = false;
            if (id) cursor = id;
            retry = 1000;
          }
        }
      }
    } catch (error) {
      if (signal?.aborted) return;
      if (applicationFailed || error.fatal) throw error;
      // Network interruptions replay from cursor. Apply/checkpoint must be idempotent.
    } finally {
      if (reader) { await reader.cancel().catch(() => {}); reader.releaseLock(); }
    }
    await delay(retry);
    retry = Math.min(30000, retry * 2);
  }
}
