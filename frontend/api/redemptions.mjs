/**
 * Call after the user actually applies/confirms a stack, never on recommendation.
 * @param {import('../../shared/types').StackResult} stack
 * @param {{baseUrl: string, userId: string, fetchImpl?: typeof fetch}} options
 * @returns {Promise<import('../../shared/types').Reward[]>}
 */
export async function redeemAppliedStack(stack, { baseUrl, userId, fetchImpl = fetch }) {
  const rewards = [];
  for (const chosen of stack.chosen_rewards) {
    const response = await fetchImpl(
      `${baseUrl.replace(/\/$/, '')}/rewards/${encodeURIComponent(chosen.reward_id)}/redeem`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Id': userId },
        body: JSON.stringify({ saved: String(chosen.savings) }),
      },
    );
    if (!response.ok) {
      // Retrying the complete stack is safe: the server records each reward once.
      throw new Error(`Could not record reward ${chosen.reward_id}: HTTP ${response.status}`);
    }
    rewards.push(await response.json());
  }
  return rewards;
}
