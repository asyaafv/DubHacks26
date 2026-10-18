import { useState } from 'react';

interface CopyCodeProps {
  code: string;
  tone?: 'default' | 'light';
  testId?: string;
}

async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    const area = document.createElement('textarea');
    area.value = value;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.left = '-9999px';
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand('copy');
    area.remove();
    return copied;
  }
}

export function CopyCode({ code, tone = 'default', testId = 'reward-code' }: CopyCodeProps) {
  const [copied, setCopied] = useState(false);
  const light = tone === 'light';

  return (
    <button
      type="button"
      data-testid={testId}
      title="Copy code"
      onClick={() => {
        void copyText(code).then((ok) => {
          if (!ok) return;
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1200);
        });
      }}
      className={`mt-2 inline-flex items-center gap-2 rounded-lg px-2 py-1 font-mono text-xs ${
        light ? 'bg-white/15 text-white hover:bg-white/25' : 'bg-stone-100 text-lapse hover:bg-stone-200'
      }`}
    >
      <span>{code}</span>
      <span className={`text-[10px] uppercase tracking-wide ${light ? 'text-white/80' : 'text-stone-500'}`}>
        {copied ? 'Copied' : 'Copy'}
      </span>
    </button>
  );
}
