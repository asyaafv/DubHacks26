import { useState } from 'react';

interface StoreLogoProps {
  domain: string;
  name: string;
  /** Tailwind size classes for the square, e.g. "h-8 w-8". */
  size?: string;
}

export function StoreLogo({ domain, name, size = 'h-10 w-10' }: StoreLogoProps) {
  const [loaded, setLoaded] = useState(false);
  const letter = (name.trim()[0] || '?').toUpperCase();

  return (
    <div className={`relative ${size} shrink-0`} data-testid="store-logo">
      <div
        className={`flex h-full w-full items-center justify-center border-2 border-ink bg-sky font-display text-sm font-black text-ink ${
          loaded ? 'hidden' : ''
        }`}
      >
        {letter}
      </div>
      {domain ? (
        <img
          src={`https://logo.clearbit.com/${domain}`}
          alt=""
          className={`absolute inset-0 h-full w-full border-2 border-ink bg-white object-contain ${loaded ? '' : 'hidden'}`}
          onLoad={() => setLoaded(true)}
          onError={() => setLoaded(false)}
        />
      ) : null}
    </div>
  );
}
