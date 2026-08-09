"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
      <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold tracking-[-0.02em] text-fg">
        Log in
      </h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
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
          className="rounded-input border border-border bg-surface px-4 py-3 text-fg placeholder:text-fg-subtle outline-none focus:border-border-strong"
        />
        {error && <p className="text-sm text-fg-muted">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="rounded-pill bg-accent px-4 py-3 font-medium text-black transition-opacity disabled:opacity-50"
        >
          {submitting ? "Logging in…" : "Log in"}
        </button>
      </form>
      <p className="text-sm text-fg-muted">
        No account?{" "}
        <Link href="/register" className="text-fg underline underline-offset-2">
          Register
        </Link>
      </p>
    </main>
  );
}
