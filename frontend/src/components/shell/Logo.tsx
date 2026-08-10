// Rebuilt sunburst mark (PRD §15.0) — the shipped `logo_original.svg` is an
// 8-spoke cross with a filled centre circle and doesn't match the mockup's
// dense radial burst (see design/logo_area.png, design/left_rail.png).
// Instead of hand-writing ~24 paths, each tapered ray is generated from its
// index: a thin "leaf" outline (stroke only, no fill) running from an inner
// radius out to a point, gently bowed via quadratic curves so it reads as
// tapered rather than a straight wedge. No centre circle, transparent
// background, viewBox matches the original file's for drop-in use.

const RAY_COUNT = 24;
const CENTER = 64;
const INNER_RADIUS = 10;
const OUTER_RADIUS = 58;
const BASE_HALF_WIDTH = 2.2;

function rayPath(index: number): string {
  const angle = (index / RAY_COUNT) * Math.PI * 2 - Math.PI / 2;
  const perp = angle + Math.PI / 2;
  // Every third ray is shortened slightly so the burst reads as dense and
  // organic rather than a mechanically perfect gear.
  const outer = OUTER_RADIUS - (index % 3 === 0 ? 6 : 0);

  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const pCos = Math.cos(perp);
  const pSin = Math.sin(perp);

  const baseLeftX = CENTER + cos * INNER_RADIUS + pCos * BASE_HALF_WIDTH;
  const baseLeftY = CENTER + sin * INNER_RADIUS + pSin * BASE_HALF_WIDTH;
  const baseRightX = CENTER + cos * INNER_RADIUS - pCos * BASE_HALF_WIDTH;
  const baseRightY = CENTER + sin * INNER_RADIUS - pSin * BASE_HALF_WIDTH;
  const tipX = CENTER + cos * outer;
  const tipY = CENTER + sin * outer;

  const midRadius = INNER_RADIUS + (outer - INNER_RADIUS) * 0.55;
  const bow = BASE_HALF_WIDTH * 0.55;
  const ctrlLeftX = CENTER + cos * midRadius + pCos * bow;
  const ctrlLeftY = CENTER + sin * midRadius + pSin * bow;
  const ctrlRightX = CENTER + cos * midRadius - pCos * bow;
  const ctrlRightY = CENTER + sin * midRadius - pSin * bow;

  return [
    `M ${baseLeftX.toFixed(2)} ${baseLeftY.toFixed(2)}`,
    `Q ${ctrlLeftX.toFixed(2)} ${ctrlLeftY.toFixed(2)} ${tipX.toFixed(2)} ${tipY.toFixed(2)}`,
    `Q ${ctrlRightX.toFixed(2)} ${ctrlRightY.toFixed(2)} ${baseRightX.toFixed(2)} ${baseRightY.toFixed(2)}`,
    "Z",
  ].join(" ");
}

const RAYS = Array.from({ length: RAY_COUNT }, (_, i) => rayPath(i));

interface LogoProps {
  size?: number;
  strokeWidth?: number;
  className?: string;
}

export function Logo({ size = 32, strokeWidth = 1.5, className }: LogoProps) {
  return (
    <svg
      viewBox="0 0 128 128"
      width={size}
      height={size}
      className={className}
      fill="none"
      stroke="#fff"
      strokeWidth={strokeWidth}
      strokeLinejoin="round"
      role="img"
      aria-label="Axiom"
    >
      {RAYS.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}
