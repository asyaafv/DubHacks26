/**
 * Fetch-based SSE client, vendored from backend/decisions/delivery/fetch-events.mjs
 * (TypeScript adaptation). Native EventSource cannot send the X-User-Id or
 * Last-Event-ID headers the backend expects, so we stream with fetch instead.
 */

export interface ServerEvent {
  event_type: string
  timestamp?: string
  user_id?: string
  reward_id?: string | null
  data?: Record<string, unknown>
}

export interface ConnectOptions {
  url: string
  userId: string
  lastEventId?: string
  signal: AbortSignal
  apply: (event: ServerEvent, id: string, type: string) => Promise<void> | void
}

export async function connectEvents({ url, userId, lastEventId = '', apply, signal }: ConnectOptions): Promise<void> {
  let cursor = lastEventId
  let retry = 1000
  const delay = (ms: number) =>
    new Promise<void>((resolve) => {
      if (signal.aborted) return resolve()
      const done = () => {
        clearTimeout(timer)
        signal.removeEventListener('abort', done)
        resolve()
      }
      const timer = setTimeout(done, ms)
      signal.addEventListener('abort', done, { once: true })
    })

  while (!signal.aborted) {
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
    try {
      const response = await fetch(url, {
        headers: {
          'X-User-Id': userId,
          Accept: 'text/event-stream',
          ...(cursor ? { 'Last-Event-ID': cursor } : {}),
        },
        cache: 'no-store',
        signal,
      })
      if (!response.ok) throw new Error(`SSE HTTP ${response.status}`)
      if (!response.headers.get('content-type')?.startsWith('text/event-stream') || !response.body) {
        throw new Error('Expected an SSE response')
      }
      reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!signal.aborted) {
        const { value, done } = await reader.read()
        if (done) break // An incomplete final frame is replayed after reconnect.
        buffer += decoder.decode(value, { stream: true })
        if (buffer.length > 1024 * 1024) throw new Error('SSE frame too large')
        let boundary: number
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          let id = ''
          let type = 'message'
          const data: string[] = []
          for (const line of frame.split('\n')) {
            if (line.startsWith('id: ')) id = line.slice(4)
            else if (line.startsWith('event: ')) type = line.slice(7)
            else if (line.startsWith('data: ')) data.push(line.slice(6))
          }
          if (data.length) {
            await apply(JSON.parse(data.join('\n')) as ServerEvent, id, type)
            if (id) cursor = id
            retry = 1000
          }
        }
      }
    } catch {
      if (signal.aborted) return
      // Network interruptions reconnect from the cursor with backoff below.
    } finally {
      if (reader) {
        await reader.cancel().catch(() => {})
        reader.releaseLock()
      }
    }
    await delay(retry)
    retry = Math.min(30000, retry * 2)
  }
}
