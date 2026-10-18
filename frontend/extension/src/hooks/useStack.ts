import { useEffect, useState } from 'react';
import type { RpcResult } from '../core/messages';
import { sendMessage } from '../core/runtime';
import type { StackResult } from '../types';

export function useStack(domain: string) {
  const [cartTotal, setCartTotal] = useState('');
  const [stack, setStack] = useState<StackResult | null>(null);
  const [stacking, setStacking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setStack(null);
    setError(null);
  }, [domain]);

  async function calculate() {
    const amount = Number(cartTotal);
    if (!domain) return;
    if (!Number.isFinite(amount) || amount <= 0) {
      setError('Enter a cart total greater than 0.');
      setStack(null);
      return;
    }
    setStacking(true);
    setError(null);
    try {
      const response = await sendMessage<RpcResult<StackResult>>({
        type: 'CALCULATE_STACK',
        domain,
        cartTotal: cartTotal.trim(),
      });
      if (!response.ok) {
        setStack(null);
        setError(response.error);
      } else {
        setStack(response.data);
      }
    } catch (err) {
      setStack(null);
      setError(err instanceof Error ? err.message : 'Could not calculate a stack.');
    } finally {
      setStacking(false);
    }
  }

  return { cartTotal, setCartTotal, stack, stacking, error, calculate };
}
