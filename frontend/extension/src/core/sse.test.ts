import { describe, expect, it } from 'vitest';
import { feedSseBuffer } from './sse';
import { EventType } from '../types';

describe('sse parser', () => {
  it('reads a reward_added frame', () => {
    const payload = {
      event_type: EventType.reward_added,
      user_id: '00000000-0000-0000-0000-000000000001',
      reward_id: '22222222-2222-2222-2222-222222222201',
      data: { code: 'HCOFALL10' },
    };
    const raw = `event: reward_added\ndata: ${JSON.stringify(payload)}\n\n`;
    const { frames, rest } = feedSseBuffer(raw);
    expect(rest).toBe('');
    expect(frames).toHaveLength(1);
    expect(frames[0]?.event).toBe('reward_added');
    expect(JSON.parse(frames[0]?.data ?? '{}').data.code).toBe('HCOFALL10');
  });
});
