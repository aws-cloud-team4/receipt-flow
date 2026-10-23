import { useReducedMotion } from "./motion";

// Two routes across the hero: a light-blue tube with a thin dark line through it, and small groups
// of green dots moving very slowly along. Pale blocks with a yellow wash sit behind. Ambient motion: the layers
// drift a few pixels on long, different cycles (landing.css .lp-amb), slow enough to go unnoticed.
const ROUTE_A = "M 470 -20 C 430 60, 470 140, 560 150 S 760 90, 900 60 S 1120 -10, 1260 20";
const ROUTE_B = "M 1260 250 C 1120 200, 980 230, 860 280 S 600 330, 560 300 S 560 200, 660 190 S 860 220, 980 330 S 1080 460, 1260 440";

function Mover({ path, dur, begin, children }: { path: string; dur: number; begin: number; children: React.ReactNode }) {
  return (
    <g>
      {children}
      <animateMotion path={path} dur={`${dur}s`} begin={`${begin}s`} repeatCount="indefinite" rotate="0" />
    </g>
  );
}

/** A small group of dots riding a route together: `count` movers a few seconds apart, so they stay
 * close on the curve. Negative begins start them mid-route, already spread out. */
function Cluster({ path, dur, at, count, gap }: { path: string; dur: number; at: number; count: number; gap: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <Mover key={i} path={path} dur={dur} begin={-(at * dur + i * gap)}>
          <circle r="4.5" className="lp-dot" />
        </Mover>
      ))}
    </>
  );
}

export default function HeroArt() {
  const reduced = useReducedMotion();
  return (
    <div className="lp-art" aria-hidden>
      <svg className="lp-art-svg" viewBox="0 0 1200 420" preserveAspectRatio="xMaxYMid slice">
        <defs>
          <linearGradient id="lpWash" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#fbf6a6" />
            <stop offset="0.55" stopColor="#f3f1d8" />
            <stop offset="1" stopColor="#dfe5fb" stopOpacity="0.2" />
          </linearGradient>
          <linearGradient id="lpPale" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#e7ebfd" stopOpacity="0.95" />
            <stop offset="1" stopColor="#c9d3fa" stopOpacity="0.55" />
          </linearGradient>
          <filter id="lpGrain">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" />
            <feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.08 0" />
            <feComposite in2="SourceGraphic" operator="in" />
          </filter>
        </defs>

        <g className="lp-amb a1">
          <rect x="740" y="0" width="180" height="60" fill="url(#lpPale)" />
          <rect x="1010" y="120" width="190" height="300" fill="url(#lpPale)" />
          <rect x="820" y="360" width="170" height="60" fill="url(#lpPale)" />
        </g>
        <g className="lp-amb a2">
          <rect x="850" y="60" width="210" height="230" fill="url(#lpWash)" />
          <rect x="850" y="60" width="210" height="230" fill="#fff" filter="url(#lpGrain)" />
          <rect x="1060" y="300" width="140" height="120" fill="url(#lpWash)" opacity="0.8" />
        </g>

        <g className="lp-amb a3">
          {[ROUTE_A, ROUTE_B].map((d, i) => (
            <g key={i}>
              <path d={d} className="lp-tube" />
              <path d={d} className="lp-wire" />
            </g>
          ))}
          {!reduced && (
            <>
              {/* very slow: one lap takes 140-180s (about 10px a second); groups of 3, 1 and 4 */}
              <Cluster path={ROUTE_A} dur={140} at={0.35} count={3} gap={1.1} />
              <Cluster path={ROUTE_B} dur={180} at={0.2} count={1} gap={0.9} />
              <Cluster path={ROUTE_B} dur={180} at={0.65} count={4} gap={0.9} />
            </>
          )}
        </g>
      </svg>
    </div>
  );
}
