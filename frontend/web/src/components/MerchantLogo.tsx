import { useState } from 'react'

export function MerchantLogo({
  name,
  domain,
  size = 40,
}: {
  name: string
  domain: string | null
  size?: number
}) {
  const [failed, setFailed] = useState(false)
  const letter = name.trim().charAt(0).toUpperCase() || '?'
  const frame = {
    width: size,
    height: size,
  }

  if (!domain || failed) {
    return (
      <div
        aria-hidden
        className="grid shrink-0 place-items-center rounded-xl bg-accent-soft text-sm font-semibold text-accent"
        style={frame}
      >
        {letter}
      </div>
    )
  }

  return (
    <img
      src={`https://logo.clearbit.com/${domain}`}
      alt=""
      width={size}
      height={size}
      referrerPolicy="no-referrer"
      className="shrink-0 rounded-xl bg-white object-contain"
      style={frame}
      onError={() => setFailed(true)}
    />
  )
}
