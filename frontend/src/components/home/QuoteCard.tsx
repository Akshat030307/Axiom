"use client";

import { Quote, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";

// Decorative and static — there is no backend endpoint for quotes or
// feedback. The thumbs are local UI state only, not wired to any API.
const QUOTES = [
  {
    text: "Research is seeing what everybody else has seen, and thinking what nobody else has thought.",
    author: "Albert Szent-Györgyi",
  },
  {
    text: "The good thing about science is that it's true whether or not you believe in it.",
    author: "Neil deGrasse Tyson",
  },
  {
    text: "Somewhere, something incredible is waiting to be known.",
    author: "Carl Sagan",
  },
] as const;

function pickQuote() {
  return QUOTES[Math.floor(Math.random() * QUOTES.length)];
}

export function QuoteCard() {
  const [quote] = useState(pickQuote);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);

  return (
    <section className="flex flex-col gap-5 rounded-card border border-border bg-surface p-6">
      <Quote size={20} className="text-fg-subtle" />
      <p className="font-[family-name:var(--font-display)] text-lg leading-snug text-fg">{quote.text}</p>
      <p className="text-sm text-fg-muted">— {quote.author}</p>
      <div className="flex items-center justify-between border-t border-border pt-4 text-sm text-fg-muted">
        <span>How was this research?</span>
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label="Helpful"
            aria-pressed={feedback === "up"}
            onClick={() => setFeedback("up")}
            className={`transition-colors ${feedback === "up" ? "text-fg" : "hover:text-fg"}`}
          >
            <ThumbsUp size={16} />
          </button>
          <button
            type="button"
            aria-label="Not helpful"
            aria-pressed={feedback === "down"}
            onClick={() => setFeedback("down")}
            className={`transition-colors ${feedback === "down" ? "text-fg" : "hover:text-fg"}`}
          >
            <ThumbsDown size={16} />
          </button>
        </div>
      </div>
    </section>
  );
}
