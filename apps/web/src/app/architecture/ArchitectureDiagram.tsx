type Node = { id: string; x: number; y: number; w: number; h: number; title: string; sub: string[]; tone?: "accent" | "blue" | "violet" | "amber" };

const NODES: Node[] = [
  { id: "browser", x: 10, y: 170, w: 150, h: 84, title: "Browser", sub: ["Next.js · Monaco", "EventSource (SSE)"] },
  { id: "api", x: 280, y: 170, w: 200, h: 84, title: "API", sub: ["FastAPI · auth · rate limit", "SSE realtime gateway"], tone: "blue" },
  { id: "redis", x: 540, y: 24, w: 220, h: 96, title: "Redis", sub: ["streams: cf:q:run / cf:q:submit", "events · cache · buckets", "worker heartbeats"], tone: "violet" },
  { id: "pg", x: 540, y: 310, w: 200, h: 84, title: "PostgreSQL", sub: ["source of truth", "row locks · fencing · audit"], tone: "amber" },
  { id: "workers", x: 800, y: 160, w: 190, h: 104, title: "Worker pool", sub: ["consumer group 'judges'", "claim CAS · lease · sweeper", "judge (normalise + compare)"], tone: "accent" },
  { id: "sandbox", x: 800, y: 330, w: 190, h: 84, title: "Sandbox", sub: ["ephemeral container", "runner → cf-launch → program"], tone: "accent" },
];

const TONE: Record<NonNullable<Node["tone"]> | "none", string> = {
  accent: "stroke-accent/60", blue: "stroke-blue/60", violet: "stroke-violet/60", amber: "stroke-amber/60", none: "stroke-line-strong",
};

type Edge = { d: string; label: string; lx: number; ly: number; dashed?: boolean; anchor?: "start" | "middle" | "end" };
const EDGES: Edge[] = [
  { d: "M160 200 H280", label: "POST /submit", lx: 220, ly: 192 },
  { d: "M280 228 H160", label: "SSE events", lx: 220, ly: 244, dashed: true },
  { d: "M360 170 V72 H540", label: "XADD job", lx: 370, ly: 64, anchor: "start" },
  { d: "M540 100 H430 V170", label: "XREAD events", lx: 440, ly: 116, dashed: true, anchor: "start" },
  { d: "M360 254 V352 H540", label: "INSERT · read", lx: 370, ly: 346, anchor: "start" },
  { d: "M760 72 H895 V160", label: "XREADGROUP / XACK", lx: 770, ly: 64, anchor: "start" },
  { d: "M800 190 H780 V104 H760", label: "publish events", lx: 775, ly: 148, dashed: true, anchor: "end" },
  { d: "M800 240 H770 V352 H740", label: "fenced commit", lx: 765, ly: 300, anchor: "end" },
  { d: "M895 264 V330", label: "docker run -i", lx: 905, ly: 302, anchor: "start" },
];

export function ArchitectureDiagram() {
  return (
    <>
      <div className="hidden overflow-x-auto p-4 md:block">
        <svg viewBox="0 0 1000 430" className="h-auto w-full min-w-[760px]" role="img" aria-label="CodeForge architecture diagram">
          <defs>
            <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 L8 4 L0 8 z" className="fill-muted" />
            </marker>
          </defs>
          {EDGES.map((e, i) => (
            <g key={i}>
              <path d={e.d} fill="none" strokeWidth={1.2} markerEnd="url(#arrow)"
                className={e.dashed ? "stroke-dim" : "stroke-muted"} strokeDasharray={e.dashed ? "4 4" : undefined}>
                {e.dashed && <animate attributeName="stroke-dashoffset" from="16" to="0" dur="1.2s" repeatCount="indefinite" />}
              </path>
              <text x={e.lx} y={e.ly} textAnchor={e.anchor ?? "middle"} className="fill-muted font-mono" fontSize={10.5}>{e.label}</text>
            </g>
          ))}
          {NODES.map((n) => (
            <g key={n.id}>
              {n.id === "workers" && (
                <>
                  <rect x={n.x + 8} y={n.y - 8} width={n.w} height={n.h} className="fill-panel stroke-line" />
                  <rect x={n.x + 4} y={n.y - 4} width={n.w} height={n.h} className="fill-panel stroke-line" />
                </>
              )}
              <rect x={n.x} y={n.y} width={n.w} height={n.h} className={`fill-panel-2 ${TONE[n.tone ?? "none"]}`} strokeWidth={1.2} />
              <text x={n.x + 12} y={n.y + 22} className="fill-fg font-mono" fontSize={13} fontWeight={600} letterSpacing="0.06em">{n.title.toUpperCase()}</text>
              {n.sub.map((s, i) => (
                <text key={i} x={n.x + 12} y={n.y + 42 + i * 16} className="fill-muted font-mono" fontSize={10.5}>{s}</text>
              ))}
            </g>
          ))}
        </svg>
      </div>
      <ol className="space-y-px bg-line md:hidden">
        {[
          ["Browser", "POST /submissions → 202 + id; opens EventSource"],
          ["API", "validates, persists row (CREATED), XADD, flips to QUEUED"],
          ["Redis Streams", "consumer group hands the job to one worker"],
          ["Worker", "row-locked claim, lease, starts a sandbox"],
          ["Sandbox", "compile + run each test under rlimits as uid 65534"],
          ["Worker", "judges outputs, fenced commit to PostgreSQL, XACK"],
          ["Redis → API → Browser", "events stream back over SSE in real time"],
        ].map(([t, d], i) => (
          <li key={i} className="bg-panel px-4 py-3">
            <div className="font-mono text-[12px] font-semibold tracking-wider text-fg"><span className="text-accent">{i + 1}.</span> {t}</div>
            <div className="mt-0.5 font-mono text-[11px] text-muted">{d}</div>
          </li>
        ))}
      </ol>
    </>
  );
}
