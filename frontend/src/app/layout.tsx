import { Inter, Inter_Tight } from "next/font/google";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Providers } from "./providers";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-inter" });
const interTight = Inter_Tight({ subsets: ["latin"], display: "swap", variable: "--font-inter-tight" });

export const metadata: Metadata = {
  title: "Axiom",
  description: "Research, without the noise.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${interTight.variable}`} suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
