/** Small dependency-free SVG charts for the dashboard. Values are passed in as measured. */

export function HourlyBars({ data }: { data: { hour: string; total: number; accepted: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.total));
  const W = 720, H = 140, gap = 3;
  const bw = (W - gap * (data.length - 1)) / Math.max(1, data.length);
  return (
    <svg viewBox={`0 0 ${W} ${H + 18}`} className="h-auto w-full" role="img" aria-label="Submissions per hour, last 24 hours">
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <line key={f} x1={0} x2={W} y1={H - f * H} y2={H - f * H} stroke="currentColor" className="text-line" strokeDasharray="2 4" />
      ))}
      {data.map((d, i) => {
        const x = i * (bw + gap);
        const th = (d.total / max) * H;
        const ah = (d.accepted / max) * H;
        const label = new Date(d.hour).getHours().toString().padStart(2, "0");
        return (
          <g key={d.hour}>
            <title>{`${label}:00 — ${d.total} submissions, ${d.accepted} accepted`}</title>
            <rect x={x} y={H - th} width={bw} height={th} className="fill-line-strong" />
            <rect x={x} y={H - ah} width={bw} height={ah} className="fill-accent/80" />
            {i % 3 === 0 && (
              <text x={x + bw / 2} y={H + 13} textAnchor="middle" className="fill-dim font-mono" fontSize={9}>{label}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function HBars({ rows, colorFor }: { rows: { label: string; value: number }[]; colorFor: (label: string) => string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  const total = rows.reduce((a, r) => a + r.value, 0);
  return (
    <ul className="space-y-2">
      {rows.map((r) => (
        <li key={r.label} className="grid grid-cols-[9.5rem_1fr_4.5rem] items-center gap-3 font-mono text-[11px]">
          <span className="truncate text-muted">{r.label.replaceAll("_", " ").toLowerCase()}</span>
          <span className="h-2 bg-panel-2">
            <span className={`block h-full ${colorFor(r.label)}`} style={{ width: `${(r.value / max) * 100}%` }} />
          </span>
          <span className="text-right text-fg">{r.value}<span className="text-dim"> {total ? `${Math.round((r.value / total) * 100)}%` : ""}</span></span>
        </li>
      ))}
      {rows.length === 0 && <li className="font-mono text-[11px] text-dim">no data yet</li>}
    </ul>
  );
}
