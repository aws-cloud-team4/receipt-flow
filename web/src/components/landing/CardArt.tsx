// Art for the three feature cards (top image area). Drawn in SVG; motion is CSS and stops
// under prefers-reduced-motion.

/** Neon wireframe receipts on a dark field with a scan beam passing over them. */
export function ScanArt() {
  const receipt = (x: number, y: number, w: number, h: number, c: string) => (
    <g stroke={c} strokeWidth="2" fill="none">
      <path d={`M${x} ${y} h${w} v${h} l-${w / 6} -8 l-${w / 6} 8 l-${w / 6} -8 l-${w / 6} 8 l-${w / 6} -8 l-${w / 6} 8 z`} />
      <line x1={x + 10} y1={y + 18} x2={x + w - 14} y2={y + 18} />
      <line x1={x + 10} y1={y + 32} x2={x + w - 30} y2={y + 32} />
      <line x1={x + 10} y1={y + 46} x2={x + w - 20} y2={y + 46} />
    </g>
  );
  return (
    <svg viewBox="0 0 380 212" className="lp-cardart dark" aria-hidden>
      <defs>
        <linearGradient id="beam" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#5ef0ff" stopOpacity="0" />
          <stop offset="0.5" stopColor="#5ef0ff" stopOpacity="0.55" />
          <stop offset="1" stopColor="#5ef0ff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect width="380" height="212" fill="#120a2a" />
      {receipt(40, 40, 96, 120, "#ff5fb4")}
      {receipt(150, 24, 110, 150, "#7c8bff")}
      {receipt(276, 54, 80, 104, "#3fe3c8")}
      <g stroke="#f7c948" strokeWidth="2" fill="none" opacity="0.9">
        <rect x="18" y="150" width="18" height="18" /><rect x="350" y="20" width="14" height="14" /><rect x="120" y="176" width="12" height="12" />
      </g>
      <rect className="lp-beam" x="0" y="-30" width="380" height="60" fill="url(#beam)" />
    </svg>
  );
}

/** Chat bubbles floating on a violet-to-amber field. */
export function ChatArt() {
  return (
    <svg viewBox="0 0 380 212" className="lp-cardart" aria-hidden>
      <defs>
        <linearGradient id="dusk" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#7d6cf2" />
          <stop offset="0.6" stopColor="#d58ad8" />
          <stop offset="1" stopColor="#f6b16c" />
        </linearGradient>
      </defs>
      <rect width="380" height="212" fill="url(#dusk)" />
      <ellipse cx="190" cy="196" rx="150" ry="22" fill="#fff" opacity="0.18" />
      <g className="lp-bob">
        <rect x="56" y="40" width="170" height="44" rx="18" fill="#fff" />
        <rect x="74" y="56" width="110" height="7" rx="3.5" fill="#7d6cf2" opacity="0.7" />
        <rect x="74" y="68" width="70" height="7" rx="3.5" fill="#c9c2f6" />
      </g>
      <g className="lp-bob d2">
        <rect x="178" y="96" width="140" height="38" rx="16" fill="#161d26" />
        <rect x="196" y="111" width="80" height="7" rx="3.5" fill="#fff" opacity="0.85" />
      </g>
      <g className="lp-bob d3">
        <rect x="70" y="146" width="96" height="30" rx="15" fill="#fff" opacity="0.92" />
        <rect x="174" y="146" width="120" height="30" rx="15" fill="#fff" opacity="0.92" />
        <rect x="86" y="158" width="60" height="6" rx="3" fill="#0972d3" />
        <rect x="190" y="158" width="84" height="6" rx="3" fill="#0972d3" />
      </g>
    </svg>
  );
}

/** Amount bars rising to a total line with a check, on a coral gradient. */
export function CheckArt() {
  const bars = [62, 40, 22, 124];
  return (
    <svg viewBox="0 0 380 212" className="lp-cardart" aria-hidden>
      <defs>
        <linearGradient id="coral" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ff8a5c" />
          <stop offset="0.55" stopColor="#ff5f7e" />
          <stop offset="1" stopColor="#c94dd8" />
        </linearGradient>
      </defs>
      <rect width="380" height="212" fill="url(#coral)" />
      <line x1="40" y1="56" x2="340" y2="56" stroke="#fff" strokeWidth="2" strokeDasharray="6 6" opacity="0.8" />
      {bars.map((h, i) => (
        <rect key={i} className="lp-bar" style={{ animationDelay: `${i * 0.15}s` }}
          x={70 + i * 62} y={180 - h} width="40" height={h} rx="4"
          fill={i === 3 ? "#fff" : "#ffe08a"} opacity={i === 3 ? 0.95 : 0.9} />
      ))}
      <text x="128" y="128" fill="#fff" fontSize="22" fontWeight="700">+</text>
      <text x="190" y="150" fill="#fff" fontSize="22" fontWeight="700">+</text>
      <text x="252" y="170" fill="#fff" fontSize="22" fontWeight="700">=</text>
      <g className="lp-pop">
        <circle cx="318" cy="56" r="20" fill="#161d26" />
        <path d="M309 56 l6 6 l12 -13" stroke="#5ee36a" strokeWidth="4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}
