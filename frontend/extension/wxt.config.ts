import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'wxt';

const extensionRoot = dirname(fileURLToPath(import.meta.url));

/** VITE_API_BASE from the shell, falling back to the .env files, so the manifest
 * host_permissions always cover the backend origin the bundle was built against. */
function apiBaseOrigin(): string | null {
  let raw = process.env.VITE_API_BASE?.trim();
  if (!raw) {
    for (const file of ['.env.production', '.env.development', '.env']) {
      try {
        const match = readFileSync(resolve(extensionRoot, file), 'utf8')
          .match(/^VITE_API_BASE=(.+)$/m);
        if (match?.[1]?.trim()) {
          raw = match[1].trim();
          break;
        }
      } catch {
        // Optional file.
      }
    }
  }
  if (!raw) return null;
  try {
    return new URL(raw).origin;
  } catch {
    return null;
  }
}

const hostPermissions = new Set(['http://localhost:8000/*', 'http://127.0.0.1:8000/*']);
const origin = apiBaseOrigin();
if (origin) hostPermissions.add(`${origin}/*`);

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
    host_permissions: [...hostPermissions],
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
