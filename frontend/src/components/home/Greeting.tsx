function timeGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function Greeting({ name }: { name: string }) {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="font-[family-name:var(--font-display)] text-4xl font-semibold tracking-[-0.02em] text-fg">
        {timeGreeting()}, {name}.
      </h1>
      <p className="text-lg text-fg-muted">What do you want to discover today?</p>
    </div>
  );
}
