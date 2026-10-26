"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const LINKS = [
  { href: "/problems", label: "problems" },
  { href: "/submissions", label: "submissions" },
  { href: "/dashboard", label: "dashboard" },
  { href: "/architecture", label: "architecture" },
];

function WorkerPulse() {
  const [workers, setWorkers] = useState<number | null>(null);
  const [ok, setOk] = useState(true);
  useEffect(() => {
    let alive = true;
    const tick = () =>
      api<{ active_workers: number | null }>("/stats/overview")
        .then((d) => { if (alive) { setWorkers(d.active_workers); setOk(true); } })
        .catch(() => alive && setOk(false));
    tick();
    const t = setInterval(tick, 10000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  const live = ok && (workers ?? 0) > 0;
  return (
    <span className="hidden items-center gap-2 font-mono text-[11px] text-muted md:flex" title="Workers with a live Redis heartbeat">
      <span className={`h-1.5 w-1.5 rounded-full ${live ? "bg-accent animate-pulse-dot" : ok ? "bg-amber" : "bg-red"}`} />
      {ok ? `${workers ?? "–"} worker${workers === 1 ? "" : "s"} online` : "api unreachable"}
    </span>
  );
}

export function Nav() {
  const path = usePathname();
  const router = useRouter();
  const { user, logout, loading } = useAuth();
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur">
      <div className="mx-auto flex h-12 max-w-[1600px] items-center gap-6 px-4">
        <Link href="/" className="flex items-center gap-2 font-mono text-[13px] font-semibold tracking-[0.18em] text-fg">
          <span className="grid h-5 w-5 place-items-center border border-accent/60 text-[10px] text-accent">▲</span>
          CODEFORGE
        </Link>
        <nav className="flex items-center gap-1 overflow-x-auto font-mono text-[12px]">
          {LINKS.map((l) => {
            const active = path === l.href || path.startsWith(l.href + "/");
            return (
              <Link key={l.href} href={l.href}
                className={`px-2.5 py-1 transition-colors ${active ? "text-fg" : "text-muted hover:text-fg"}`}>
                <span className={active ? "text-accent" : "text-dim"}>/</span>{l.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-4">
          <WorkerPulse />
          {loading ? null : user ? (
            <div className="flex items-center gap-3 font-mono text-[12px]">
              <span className="text-muted">~/<span className="text-fg">{user.username}</span></span>
              <button onClick={async () => { await logout(); router.push("/"); }}
                className="border border-line px-2 py-1 text-muted transition-colors hover:border-line-strong hover:text-fg">
                logout
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 font-mono text-[12px]">
              <Link href="/login" className="px-2 py-1 text-muted hover:text-fg">login</Link>
              <Link href="/register" className="border border-accent/50 px-2.5 py-1 text-accent transition-colors hover:bg-accent-soft">
                register
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
