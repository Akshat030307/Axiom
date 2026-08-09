"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useAuth } from "@/hooks/useAuth";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(email, password, displayName);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
      <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold tracking-[-0.02em] text-fg">
        Create an account
      </h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <input
          type="text"
          placeholder="Display name (optional)"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="rounded-input border border-border bg-surface px-4 py-3 text-fg placeholder:text-fg-subtle outline-none focus:border-border-strong"
        />
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="rounded-input border border-border bg-surface px-4 py-3 text-fg placeholder:text-fg-subtle outline-none focus:border-border-strong"
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
          className="rounded-input border border-border bg-surface px-4 py-3 text-fg placeholder:text-fg-subtle outline-none focus:border-border-strong"
        />
        {error && <p className="text-sm text-fg-muted">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="rounded-pill bg-accent px-4 py-3 font-medium text-black transition-opacity disabled:opacity-50"
        >
          {submitting ? "Creating account…" : "Register"}
        </button>
      </form>
      <p className="text-sm text-fg-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-fg underline underline-offset-2">
          Log in
        </Link>
      </p>
    </main>
  );
}
