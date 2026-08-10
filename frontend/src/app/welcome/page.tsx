import { LandingFeatures } from "@/components/landing/LandingFeatures";
import { LandingHero } from "@/components/landing/LandingHero";
import { LandingNav } from "@/components/landing/LandingNav";

// Deliberately outside the (app) route group: (app)/layout.tsx hard-redirects
// unauthenticated visitors to /login before this could ever render there, and
// restructuring the real dashboard off `/` to make room for this is a bigger,
// riskier change than a standalone marketing route needs to be. Sign in / Get
// Started link into the real, existing auth flow.
export default function WelcomePage() {
  return (
    <main className="min-h-screen bg-bg">
      <LandingNav />
      <LandingHero />
      <LandingFeatures />
    </main>
  );
}
