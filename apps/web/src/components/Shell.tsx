import type { ReactNode } from "react";

/** Page heading in the terminal idiom: a path-like eyebrow, a title, optional actions. */
export function PageHeader({ path, title, children }: { path: string; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
      <div>
        <div className="font-mono text-[11px] text-dim">
          <span className="text-accent">$</span> {path}
        </div>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-fg">{title}</h1>
      </div>
      {children}
    </div>
  );
}

export function Panel({ title, right, children, className = "" }: { title: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`border border-line bg-panel ${className}`}>
      <header className="flex items-center justify-between border-b border-line px-3 py-2">
        <h2 className="label">{title}</h2>
        {right}
      </header>
      <div className="p-3">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, tone = "fg" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "fg" | "accent" | "amber" | "red" }) {
  const color = { fg: "text-fg", accent: "text-accent", amber: "text-amber", red: "text-red" }[tone];
  return (
    <div className="bg-panel px-4 py-3">
      <div className="label">{label}</div>
      <div className={`mt-1 font-mono text-2xl tabular-nums ${color}`}>{value}</div>
      {hint && <div className="mt-0.5 font-mono text-[11px] text-dim">{hint}</div>}
    </div>
  );
}
