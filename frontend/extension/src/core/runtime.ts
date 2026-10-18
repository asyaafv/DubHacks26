import { DASHBOARD_URL } from '../api/config';
import type { ExtensionMessage } from './messages';

export async function sendMessage<T>(message: ExtensionMessage): Promise<T> {
  const response = await browser.runtime.sendMessage(message);
  if (response == null) {
    throw new Error('Lapse background did not respond.');
  }
  return response as T;
}

export function openDashboard(): void {
  if (typeof browser !== 'undefined' && browser.tabs?.create) {
    void browser.tabs.create({ url: DASHBOARD_URL });
    return;
  }
  window.open(DASHBOARD_URL, '_blank', 'noopener');
}
