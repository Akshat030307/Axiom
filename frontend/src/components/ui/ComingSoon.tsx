export function ComingSoon({ title }: { title: string }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-2 p-6 text-center">
      <h1 className="font-[family-name:var(--font-display)] text-xl font-medium tracking-[-0.02em] text-fg">
        {title}
      </h1>
      <p className="text-sm text-fg-muted">Coming soon.</p>
    </main>
  );
}
