import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'wxt';

const extensionRoot = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  srcDir: 'src',
  modules: ['@wxt-dev/module-react'],
  vite: () => ({
    envPrefix: ['VITE_', 'WXT_'],
    server: {
      fs: {
        allow: [resolve(extensionRoot, '../..')],
      },
    },
  }),
  manifest: {
    name: 'Lapse',
    short_name: 'Lapse',
    description: 'Find and stack store rewards, card cashback, and memberships at checkout.',
    permissions: ['storage', 'activeTab'],
    host_permissions: ['http://localhost:8000/*', 'http://127.0.0.1:8000/*'],
    action: {
      default_title: 'Lapse',
    },
    icons: {
      16: '/icon/16.png',
      32: '/icon/32.png',
      48: '/icon/48.png',
      128: '/icon/128.png',
    },
  },
});
