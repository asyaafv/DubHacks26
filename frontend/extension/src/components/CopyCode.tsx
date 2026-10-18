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
      className={`inline-flex items-center gap-2 border-2 px-2 py-1 text-xs font-black uppercase transition-transform active:translate-x-[2px] active:translate-y-[2px] active:shadow-none ${
        light
          ? 'border-lime bg-ink text-lime shadow-[2px_2px_0_#BCE740]'
          : 'border-ink bg-lime text-ink shadow-[2px_2px_0_#141414]'
      }`}
    >
      <span className="tracking-[0.15em]">{code}</span>
      <span className="text-[9px] opacity-70">{copied ? 'Copied' : 'Copy'}</span>
    </button>
  );
}
