"use client";

import { ArrowUp } from "lucide-react";
import { useRef, type ChangeEvent, type KeyboardEvent } from "react";

interface ResearchInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
}

export function ResearchInput({ value, onChange, onSubmit, disabled }: ResearchInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function autoGrow() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  }

  function handleChange(e: ChangeEvent<HTMLTextAreaElement>) {
    onChange(e.target.value);
    autoGrow();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !disabled) onSubmit();
    }
  }

  return (
    <div className="flex items-end gap-3 rounded-input border border-border bg-surface px-5 py-4">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        rows={1}
        placeholder="Ask anything… e.g. Analyze the future of fusion energy"
        className="max-h-32 flex-1 resize-none bg-transparent text-base leading-relaxed text-fg placeholder:text-fg-subtle outline-none"
      />
      <button
        type="button"
        onClick={onSubmit}
        disabled={disabled || !value.trim()}
        aria-label="Submit research query"
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent text-black transition-opacity disabled:opacity-40"
      >
        <ArrowUp size={18} strokeWidth={2.25} />
      </button>
    </div>
  );
}
