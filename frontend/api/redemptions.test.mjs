import assert from 'node:assert/strict';
import test from 'node:test';
import { redeemAppliedStack } from './redemptions.mjs';

test('records each applied reward with its exact solver savings and owner', async () => {
  const calls = [];
  const stack = {
    chosen_rewards: [
      { reward_id: 'first', savings: '12.50' },
      { reward_id: 'second', savings: '0.01' },
    ],
    card_cashback: '22.50',
    total_savings: '35.01',
  };
  const result = await redeemAppliedStack(stack, {
    baseUrl: 'https://api.example.test/', userId: 'owner',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, json: async () => ({ status: 'used' }) };
    },
  });
  assert.equal(result.length, 2);
  assert.deepEqual(calls.map(call => call.url), [
    'https://api.example.test/rewards/first/redeem',
    'https://api.example.test/rewards/second/redeem',
  ]);
  assert.deepEqual(calls.map(call => JSON.parse(call.options.body)), [
    { saved: '12.50' }, { saved: '0.01' },
  ]);
  assert.ok(calls.every(call => call.options.headers['X-User-Id'] === 'owner'));
});

test('stops on a failed redemption so the caller can retry instead of claiming success', async () => {
  let attempts = 0;
  await assert.rejects(redeemAppliedStack({ chosen_rewards: [
    { reward_id: 'first', savings: '1.00' }, { reward_id: 'second', savings: '2.00' },
  ] }, {
    baseUrl: 'https://api.example.test', userId: 'owner',
    fetchImpl: async () => { attempts += 1; return { ok: false, status: 503 }; },
  }), /HTTP 503/);
  assert.equal(attempts, 1);
});
