import { useState } from 'react';

interface StoreLogoProps {
  domain: string;
  name: string;
}

export function StoreLogo({ domain, name }: StoreLogoProps) {
  const [loaded, setLoaded] = useState(false);
  const letter = (name.trim()[0] || '?').toUpperCase();

  return (
    <div className="relative h-10 w-10 shrink-0" data-testid="store-logo">
      <div
        className={`flex h-10 w-10 items-center justify-center rounded-full bg-lapse text-sm font-semibold text-white ${
          loaded ? 'hidden' : ''
        }`}
      >
        {letter}
      </div>
      {domain ? (
        <img
          src={`https://logo.clearbit.com/${domain}`}
          alt=""
          className={`absolute inset-0 h-10 w-10 rounded-full bg-white object-contain ${loaded ? '' : 'hidden'}`}
          onLoad={() => setLoaded(true)}
          onError={() => setLoaded(false)}
        />
      ) : null}
    </div>
  );
}
