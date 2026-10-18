export interface SseFrame {
  event: string;
  data: string;
}

/** Parse one SSE block separated by a blank line. */
export function parseSseChunk(chunk: string): SseFrame | null {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of chunk.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue;
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join('\n') };
}

export function feedSseBuffer(buffer: string): { frames: SseFrame[]; rest: string } {
  const parts = buffer.split(/\r?\n\r?\n/);
  const rest = parts.pop() ?? '';
  const frames = parts
    .map((part) => parseSseChunk(part))
    .filter((frame): frame is SseFrame => frame != null);
  return { frames, rest };
}
