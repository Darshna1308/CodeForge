"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { DifficultyTag, Kbd } from "@/components/Badges";
import { PageHeader } from "@/components/Shell";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Difficulty, Page, ProblemSummary, Tag } from "@/lib/types";

const DIFFS: (Difficulty | "ALL")[] = ["ALL", "EASY", "MEDIUM", "HARD"];

export default function ProblemsPage() {
  const { user } = useAuth();
  const [problems, setProblems] = useState<ProblemSummary[] | null>(null);
  const [tags, setTags] = useState<Tag[]>([]);
  const [search, setSearch] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty | "ALL">("ALL");
  const [tag, setTag] = useState<string | null>(null);
  const [status, setStatus] = useState<"all" | "solved" | "attempted" | "todo">("all");
  const [error, setError] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Filtering is server-side (cache-aside per filter fingerprint); debounce typing.
    const t = setTimeout(() => {
      const q = new URLSearchParams();
      if (search) q.set("search", search);
      if (difficulty !== "ALL") q.set("difficulty", difficulty);
      if (tag) q.set("tag", tag);
      if (status !== "all") q.set("status", status);
      api<Page<ProblemSummary>>(`/problems?${q}`)
        .then((p) => { setProblems(p.items); setError(null); })
        .catch((e: ApiError) => setError(e.message));
    }, 150);
    return () => clearTimeout(t);
  }, [search, difficulty, tag, status, user]);

  useEffect(() => { api<Tag[]>("/problems/tags").then(setTags).catch(() => undefined); }, []);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") { e.preventDefault(); searchRef.current?.focus(); }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);

  const solved = useMemo(() => problems?.filter((p) => p.status === "solved").length ?? 0, [problems]);

  return (
    <main className="mx-auto max-w-[1600px] px-4 py-8">
      <PageHeader path="ls ./problems" title="Problem set">
        {user && problems && (
          <div className="font-mono text-[12px] text-muted">
            solved <span className="text-accent">{solved}</span> / {problems.length}
          </div>
        )}
      </PageHeader>

      <div className="mt-5 grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="space-y-6">
          <div>
            <div className="label mb-2">difficulty</div>
            <div className="flex flex-wrap gap-1 lg:flex-col">
              {DIFFS.map((d) => (
                <button key={d} onClick={() => setDifficulty(d)}
                  className={`border px-2.5 py-1 text-left font-mono text-[12px] transition-colors ${difficulty === d ? "border-accent/50 bg-accent-soft text-fg" : "border-transparent text-muted hover:text-fg"}`}>
                  {d.toLowerCase()}
                </button>
              ))}
            </div>
          </div>
          {user && (
            <div>
              <div className="label mb-2">status</div>
              <div className="flex flex-wrap gap-1 lg:flex-col">
                {(["all", "solved", "attempted", "todo"] as const).map((s) => (
                  <button key={s} onClick={() => setStatus(s)}
                    className={`border px-2.5 py-1 text-left font-mono text-[12px] transition-colors ${status === s ? "border-accent/50 bg-accent-soft text-fg" : "border-transparent text-muted hover:text-fg"}`}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div>
            <div className="label mb-2">tags</div>
            <div className="flex flex-wrap gap-1.5">
              {tags.map((t) => (
                <button key={t.slug} onClick={() => setTag(tag === t.slug ? null : t.slug)}
                  className={`border px-1.5 py-0.5 font-mono text-[11px] transition-colors ${tag === t.slug ? "border-accent/60 text-accent" : "border-line text-muted hover:border-line-strong hover:text-fg"}`}>
                  {t.slug}<span className="ml-1 text-dim">{t.count}</span>
                </button>
              ))}
            </div>
          </div>
        </aside>

        <section className="min-w-0">
          <div className="flex items-center gap-2 border border-line bg-panel px-3 focus-within:border-line-strong">
            <span className="font-mono text-[13px] text-accent">›</span>
            <input ref={searchRef} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="search problems by title or slug"
              className="h-10 w-full bg-transparent font-mono text-[13px] text-fg outline-none placeholder:text-dim" />
            <Kbd>/</Kbd>
          </div>

          <div className="mt-3 overflow-x-auto border border-line">
            <table className="w-full min-w-[720px] border-collapse font-mono text-[13px]">
              <thead>
                <tr className="border-b border-line bg-panel text-left">
                  {["", "#", "title", "difficulty", "tags", "acceptance", "judged"].map((h) => (
                    <th key={h} className="label px-3 py-2 font-normal">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {problems?.map((p) => (
                  <tr key={p.id} className="group border-b border-line/70 transition-colors last:border-0 hover:bg-panel-2">
                    <td className="w-8 px-3 py-2.5 text-center" title={p.status ?? "not attempted"}>
                      {p.status === "solved" ? <span className="text-accent">✓</span> : p.status === "attempted" ? <span className="text-amber">◐</span> : <span className="text-dim/50">·</span>}
                    </td>
                    <td className="w-10 px-3 py-2.5 text-dim">{String(p.id).padStart(2, "0")}</td>
                    <td className="px-3 py-2.5">
                      <Link href={`/problems/${p.slug}`} className="font-sans text-[14px] text-fg group-hover:text-accent">{p.title}</Link>
                    </td>
                    <td className="px-3 py-2.5"><DifficultyTag d={p.difficulty} /></td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {p.tags.map((t) => <span key={t.slug} className="text-[11px] text-dim">#{t.slug}</span>)}
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      {p.acceptance_rate === null ? <span className="text-dim">—</span> : (
                        <div className="flex items-center gap-2">
                          <span className="h-1 w-14 bg-panel-2"><span className="block h-full bg-accent/70" style={{ width: `${p.acceptance_rate}%` }} /></span>
                          <span className="text-muted">{p.acceptance_rate.toFixed(1)}%</span>
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-dim">{p.accepted}/{p.submissions}</td>
                  </tr>
                ))}
                {problems && problems.length === 0 && (
                  <tr><td colSpan={7} className="px-3 py-8 text-center text-dim">no problems match these filters</td></tr>
                )}
                {!problems && !error && (
                  <tr><td colSpan={7} className="px-3 py-8 text-center text-dim">loading<span className="animate-blink">_</span></td></tr>
                )}
                {error && <tr><td colSpan={7} className="px-3 py-8 text-center text-red">{error}</td></tr>}
              </tbody>
            </table>
          </div>
          <p className="mt-2 font-mono text-[11px] text-dim">acceptance = accepted / judged submissions · lists are served cache-aside from Redis (≤120s stale)</p>
        </section>
      </div>
    </main>
  );
}
