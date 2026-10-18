import { describe, expect, it } from 'vitest';
import { detectFromUrl, isCheckoutUrl, normalizeDomain } from './page';

describe('page detection', () => {
  it('treats a Hollister cart URL as that store checkout', () => {
    expect(normalizeDomain('www.hollisterco.com')).toBe('hollisterco.com');
    expect(isCheckoutUrl('https://www.hollisterco.com/shop/us/cart')).toBe(true);
    expect(detectFromUrl('https://hollisterco.com/cart', 'Bag')).toEqual({
      domain: 'hollisterco.com',
      isCheckout: true,
      url: 'https://hollisterco.com/cart',
      title: 'Bag',
    });
  });

  it('ignores extension and browser pages', () => {
    expect(detectFromUrl('chrome-extension://abc/popup.html')).toBeNull();
    expect(detectFromUrl('https://hollisterco.com/')).toMatchObject({ isCheckout: false });
  });
});
