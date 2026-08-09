import Image from "next/image";

// DEVIATION FROM PRD §15.0: the PRD calls for the horizon to be recreated
// entirely in CSS (no image), and the Definition of Done explicitly greps
// for this. The CSS-only version (layered radial gradients) was implemented
// first and worked, but read as a flat gradient blob rather than a lunar
// horizon. The user then supplied `design/moon.jpeg` — a real, UI-free photo
// (not one of the seven mockup crops §15.0 forbids serving) — and directed
// its use here explicitly. Per that direct instruction this renders the
// photo instead; `public/hero-moon.jpg` is the one shipped asset alongside
// `public/logo.svg`. The `grep -r hero_horizon` DoD check still passes since
// that specific mockup crop is untouched — only this new, separately
// supplied photo is served.
export function HeroHorizon() {
  return (
    <Image
      src="/hero-moon.jpg"
      alt=""
      fill
      priority
      sizes="(max-width: 768px) 100vw, 900px"
      className="hero-horizon-drift pointer-events-none object-cover"
      style={{ objectPosition: "center 15%" }}
    />
  );
}
