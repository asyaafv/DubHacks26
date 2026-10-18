# Frontend - Chrome Extension (Person 4)

WXT + React + TypeScript Chrome MV3 extension for reward discovery and stacking.

## Tech Stack

- **WXT**: Modern Chrome extension framework
- **React 18**: UI components
- **TypeScript**: Type safety
- **TailwindCSS**: Styling (optional)

## Setup

```bash
cd frontend
npm create wxt@latest . -- --template react-ts
npm install
```

## Project Structure

```
frontend/
├── src/
│   ├── entrypoints/
│   │   ├── background.ts      # Service worker
│   │   ├── content.ts         # Content script
│   │   └── popup/             # Popup UI
│   │       ├── App.tsx
│   │       ├── main.tsx
│   │       └── index.html
│   ├── components/
│   │   ├── RewardCard.tsx
│   │   ├── StackResult.tsx
│   │   └── WalletSummary.tsx
│   ├── hooks/
│   │   ├── useRewards.ts
│   │   ├── useStack.ts
│   │   └── useSSE.ts
│   ├── api/
│   │   └── client.ts          # API client
│   └── types/
│       └── index.ts           # Re-export shared types
├── wxt.config.ts
├── package.json
└── tsconfig.json
```

## Type Integration

Import types from shared contracts:

```typescript
// src/types/index.ts
export * from '../../../shared/types';

// Or copy types.ts to frontend and import locally
```

## API Client

```typescript
// src/api/client.ts
import type { 
  Reward, 
  StackRequest, 
  StackResult, 
  LookupRequest, 
  LookupResult,
  Wallet,
  SyncResponse
} from '../types';

const API_BASE = 'http://localhost:8000';

class LapseAPI {
  private userId: string;

  constructor(userId: string) {
    this.userId = userId;
  }

  private headers(): HeadersInit {
    return {
      'Content-Type': 'application/json',
      'X-User-Id': this.userId,
    };
  }

  async getWallet(): Promise<Wallet> {
    const res = await fetch(`${API_BASE}/wallet`, {
      headers: this.headers(),
    });
    return res.json();
  }

  async lookup(request: Omit<LookupRequest, 'user_id'>): Promise<LookupResult> {
    const res = await fetch(`${API_BASE}/lookup`, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify({ ...request, user_id: this.userId }),
    });
    return res.json();
  }

  async stack(request: Omit<StackRequest, 'user_id'>): Promise<StackResult> {
    const res = await fetch(`${API_BASE}/stack`, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify({ ...request, user_id: this.userId }),
    });
    return res.json();
  }

  async sync(since?: Date): Promise<SyncResponse> {
    const params = since ? `?since=${since.toISOString()}` : '';
    const res = await fetch(`${API_BASE}/sync${params}`, {
      headers: this.headers(),
    });
    return res.json();
  }
}

export const api = new LapseAPI('00000000-0000-0000-0000-000000000001');
```

## SSE Hook

```typescript
// src/hooks/useSSE.ts
import { useEffect, useState, useCallback } from 'react';
import type { Event, EventType } from '../types';

const API_BASE = 'http://localhost:8000';

export function useSSE(userId: string) {
  const [events, setEvents] = useState<Event[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const eventSource = new EventSource(`${API_BASE}/events`, {
      // Note: EventSource doesn't support custom headers
      // For hackathon, pass userId as query param or cookie
    });

    eventSource.onopen = () => {
      setConnected(true);
    };

    eventSource.onerror = () => {
      setConnected(false);
    };

    // Listen for each event type
    const eventTypes: EventType[] = [
      'reward_added',
      'reward_expiring', 
      'reward_updated',
      'reward_used',
      'sync_complete'
    ];

    eventTypes.forEach(type => {
      eventSource.addEventListener(type, (e: MessageEvent) => {
        const event = JSON.parse(e.data) as Event;
        setEvents(prev => [...prev, event]);
      });
    });

    return () => {
      eventSource.close();
    };
  }, [userId]);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  return { events, connected, clearEvents };
}
```

## Content Script

Detect current shopping site and trigger lookup:

```typescript
// src/entrypoints/content.ts
export default defineContentScript({
  matches: ['*://*/*'],
  
  async main() {
    // Get current domain
    const domain = window.location.hostname.replace('www.', '');
    
    // Check if this is a shopping site
    const checkoutIndicators = [
      '/cart', '/checkout', '/bag', '/basket',
      'add-to-cart', 'add_to_cart'
    ];
    
    const isCheckout = checkoutIndicators.some(
      indicator => window.location.href.includes(indicator)
    );
    
    // Send message to background script
    chrome.runtime.sendMessage({
      type: 'PAGE_VISIT',
      domain,
      isCheckout,
      url: window.location.href,
      title: document.title
    });
  }
});
```

## Background Script

Handle messages and coordinate API calls:

```typescript
// src/entrypoints/background.ts
import { api } from '../api/client';

export default defineBackground(() => {
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'PAGE_VISIT') {
      handlePageVisit(message).then(sendResponse);
      return true; // Keep channel open for async response
    }
    
    if (message.type === 'CALCULATE_STACK') {
      handleStackRequest(message).then(sendResponse);
      return true;
    }
  });
});

async function handlePageVisit(message: { domain: string; isCheckout: boolean }) {
  // Lookup rewards for this domain
  const result = await api.lookup({ domain: message.domain, limit: 3 });
  
  if (result.rewards.length > 0) {
    // Show badge with reward count
    chrome.action.setBadgeText({ text: String(result.rewards.length) });
    chrome.action.setBadgeBackgroundColor({ color: '#10B981' }); // Green
    
    // Store for popup
    chrome.storage.local.set({ 
      currentLookup: result,
      currentDomain: message.domain 
    });
  } else {
    chrome.action.setBadgeText({ text: '' });
  }
  
  return result;
}

async function handleStackRequest(message: { cartTotal: string; domain: string }) {
  const result = await api.stack({
    domain: message.domain,
    cart_total: message.cartTotal,
    items: []
  });
  
  return result;
}
```

## Popup UI

```tsx
// src/entrypoints/popup/App.tsx
import { useEffect, useState } from 'react';
import type { LookupResult, StackResult } from '../../types';

export default function App() {
  const [lookup, setLookup] = useState<LookupResult | null>(null);
  const [stack, setStack] = useState<StackResult | null>(null);
  const [cartTotal, setCartTotal] = useState('');
  const [domain, setDomain] = useState('');

  useEffect(() => {
    // Load current lookup from storage
    chrome.storage.local.get(['currentLookup', 'currentDomain'], (result) => {
      if (result.currentLookup) {
        setLookup(result.currentLookup);
        setDomain(result.currentDomain);
      }
    });
  }, []);

  const handleCalculateStack = async () => {
    const result = await chrome.runtime.sendMessage({
      type: 'CALCULATE_STACK',
      domain,
      cartTotal
    });
    setStack(result);
  };

  return (
    <div className="w-80 p-4">
      <h1 className="text-xl font-bold mb-4">Lapse</h1>
      
      {lookup && (
        <div className="mb-4">
          <h2 className="font-semibold">
            {lookup.merchant?.name || domain}
          </h2>
          <p className="text-sm text-gray-600">
            {lookup.rewards.length} rewards available
          </p>
          
          {lookup.rewards.map((scored, i) => (
            <div key={i} className="border rounded p-2 mt-2">
              <div className="font-medium">{scored.reward.merchant_name}</div>
              <div className="text-green-600">
                {scored.reward.kind === 'percent_off' 
                  ? `${scored.reward.value}% off`
                  : `$${scored.reward.value} off`
                }
              </div>
              {scored.reward.code && (
                <code className="bg-gray-100 px-1">{scored.reward.code}</code>
              )}
              {scored.days_until_expiry !== null && (
                <div className="text-sm text-orange-600">
                  Expires in {scored.days_until_expiry} days
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      
      <div className="border-t pt-4">
        <h2 className="font-semibold mb-2">Calculate Savings</h2>
        <input
          type="number"
          placeholder="Cart total ($)"
          value={cartTotal}
          onChange={(e) => setCartTotal(e.target.value)}
          className="border rounded px-2 py-1 w-full mb-2"
        />
        <button
          onClick={handleCalculateStack}
          className="bg-blue-500 text-white px-4 py-2 rounded w-full"
        >
          Find Best Stack
        </button>
      </div>
      
      {stack && (
        <div className="mt-4 bg-green-50 p-3 rounded">
          <div className="font-bold text-green-800">
            Save ${stack.total_savings}!
          </div>
          <div className="text-sm mt-2">{stack.explanation}</div>
        </div>
      )}
    </div>
  );
}
```

## Mock Mode

For development without backend:

```typescript
// src/api/mock.ts
import type { LookupResult, StackResult, Wallet } from '../types';

export const mockApi = {
  async lookup(): Promise<LookupResult> {
    return {
      merchant: {
        id: '11111111-1111-1111-1111-111111111110',
        name: 'Hollister',
        domain: 'hollisterco.com',
        mcc: '5651',
        category: 'Family Clothing Stores',
        aliases: [],
        logo_url: null,
        created_at: new Date().toISOString()
      },
      rewards: [
        {
          reward: {
            id: '22222222-2222-2222-2222-222222222201',
            user_id: '00000000-0000-0000-0000-000000000001',
            merchant_name: 'Hollister',
            kind: 'percent_off',
            value: '10.00',
            code: 'HCOFALL10',
            expires_at: '2026-10-20T23:59:59Z',
            // ... other fields
          },
          score: 1.85,
          value_component: 0.2,
          match_component: 1.0,
          urgency_component: 1.65,
          days_until_expiry: 2
        }
      ],
      total_available: 25
    };
  },
  
  async stack(): Promise<StackResult> {
    return {
      chosen_rewards: [],
      recommended_card: null,
      card_cashback: '0',
      original_price: '100.00',
      final_price: '90.00',
      total_savings: '10.00',
      savings_percent: '10.00',
      explanation: 'Applied HCOFALL10 for 10% off ($10.00 savings).',
      alternatives: [],
      solver_status: 'mock'
    };
  }
};
```

## Endpoints Used

| Endpoint | Method | When |
|----------|--------|------|
| `/lookup` | POST | User visits shopping site |
| `/stack` | POST | User enters cart total |
| `/wallet` | GET | Popup opened |
| `/sync` | GET | Extension loaded (fallback) |
| `/events` | GET | Real-time updates |
| `/classify-merchant` | POST | Unknown merchant detected |

## Manifest Permissions

```json
{
  "permissions": [
    "storage",
    "activeTab"
  ],
  "host_permissions": [
    "http://localhost:8000/*"
  ]
}
```

## Acceptance Criteria

- [ ] Extension installs and runs
- [ ] Content script detects shopping sites
- [ ] Popup shows available rewards
- [ ] Cart total input triggers stack calculation
- [ ] Results displayed with explanation
- [ ] SSE events update UI (or fallback to polling)
- [ ] Badge shows reward count
- [ ] Types imported from shared contracts

## Development

```bash
# Development with hot reload
npm run dev

# Build for production
npm run build

# Load unpacked extension from .output/chrome-mv3
```

## Notes

- **SSE with EventSource**: No custom headers - use query params or cookies for user ID
- **CORS**: API allows `chrome-extension://*` origins
- **Demo user**: `00000000-0000-0000-0000-000000000001`
- **Mock mode**: Use mock API for UI development without backend
