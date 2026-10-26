"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { DifficultyTag, Kbd, VerdictBadge } from "@/components/Badges";
import { ExecutionVisualizer } from "@/components/ExecutionVisualizer";
import { Markdown } from "@/components/Markdown";
import { Split } from "@/components/Split";
import { api, ApiError, newIdempotencyKey } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago, kb, ms } from "@/lib/format";
import { useSubmissionStream } from "@/lib/useSubmissionStream";
import type { Accepted, Page, ProblemDetail, SubmissionDetail, SubmissionSummary } from "@/lib/types";

import { ResultPanel } from "./ResultPanel";

const CodeEditor = dynamic(() => import("@/components/CodeEditor").then((m) => m.CodeEditor), {
  ssr: false,
  loading: () => <div className="p-4 font-mono text-xs text-dim">loading editor…</div>,
});

function draftKey(slug: string, lang: string) {
  return `cf:draft:${slug}:${lang}`;
}

export default function Workspace({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const { user } = useAuth();
  const [problem, setProblem] = useState<ProblemDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [lang, setLang] = useState("python");
  const [code, setCode] = useState("");
  const [leftTab, setLeftTab] = useState<"description" | "submissions">("description");
  const [consoleTab, setConsoleTab] = useState<"testcase" | "execution">("testcase");
  const [customOn, setCustomOn] = useState(false);
  const [customInput, setCustomInput] = useState("");
  const [activeId, setActiveId] = useState<number | null>(null);
  const [activeMode, setActiveMode] = useState<"RUN" | "SUBMIT">("RUN");
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<SubmissionSummary[]>([]);
  const pendingKey = useRef<string | null>(null);

  useEffect(() => {
    api<ProblemDetail>(`/problems/${slug}`)
      .then((p) => {
        setProblem(p);
        if (p.examples[0]) setCustomInput(p.examples[0].input);
      })
      .catch((e: ApiError) => e.status === 404 && setNotFound(true));
  }, [slug]);

  // Load the saved draft (or template) whenever the language changes.
  useEffect(() => {
    if (!problem) return;
    const tpl = problem.languages.find((l) => l.key === lang)?.template ?? "";
    let saved: string | null = null;
    try { saved = localStorage.getItem(draftKey(slug, lang)); } catch { /* ignore */ }
    setCode(saved ?? tpl);
  }, [problem, lang, slug]);

  useEffect(() => {
    if (!problem) return;
    const t = setTimeout(() => { try { localStorage.setItem(draftKey(slug, lang), code); } catch { /* ignore */ } }, 400);
    return () => clearTimeout(t);
  }, [code, lang, slug, problem]);

  const loadHistory = useCallback(() => {
    if (!user) return;
    api<Page<SubmissionSummary>>(`/submissions?problem=${slug}&page_size=50`).then((p) => setHistory(p.items)).catch(() => undefined);
  }, [slug, user]);
  useEffect(loadHistory, [loadHistory]);

  const pipeline = useSubmissionStream(activeId, (d) => {
    setDetail(d);
    setBusy(false);
    if (d?.mode === "SUBMIT") loadHistory();
  });

  const execute = useCallback(async (mode: "RUN" | "SUBMIT") => {
    if (!user || busy || !problem) return;
    setBusy(true);
    setError(null);
    setDetail(null);
    setConsoleTab("execution");
    // One key per logical click; a network retry of the same click reuses it.
    pendingKey.current = pendingKey.current ?? newIdempotencyKey();
    try {
      const body = { problem_slug: slug, language: lang, source_code: code, ...(mode === "RUN" && customOn ? { custom_input: customInput } : {}) };
      const res = await api<Accepted>(mode === "RUN" ? "/executions" : "/submissions", {
        method: "POST", json: body, headers: { "Idempotency-Key": pendingKey.current },
      });
      pendingKey.current = null;
      setActiveMode(mode);
      setActiveId(res.id);
    } catch (e) {
      const err = e as ApiError;
      if (err.status !== 0) pendingKey.current = null;
      setError(err.code === "rate_limited" ? `${err.message}` : err.message);
      setBusy(false);
    }
  }, [user, busy, problem, slug, lang, code, customOn, customInput]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === "Enter") { e.preventDefault(); void execute("SUBMIT"); }
      if (e.key === "'") { e.preventDefault(); void execute("RUN"); }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [execute]);

  if (notFound) {
    return <main className="mx-auto max-w-3xl px-4 py-20 font-mono text-sm text-muted">problem <span className="text-red">{slug}</span> not found. <Link href="/problems" className="text-accent">← back</Link></main>;
  }
  if (!problem) {
    return <main className="px-4 py-20 text-center font-mono text-sm text-dim">loading<span className="animate-blink">_</span></main>;
  }

  const language = problem.languages.find((l) => l.key === lang);

  const left = (
    <div className="flex min-h-0 flex-1 flex-col bg-panel/60">
      <div className="flex items-center gap-1 border-b border-line px-2 font-mono text-[12px]">
        {(["description", "submissions"] as const).map((t) => (
          <button key={t} onClick={() => setLeftTab(t)}
            className={`border-b px-3 py-2 transition-colors ${leftTab === t ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg"}`}>
            {t}{t === "submissions" && history.length ? <span className="ml-1 text-dim">{history.length}</span> : null}
          </button>
        ))}
      </div>
      <div className="scrollbar-thin min-h-0 flex-1 overflow-auto px-5 py-5">
        {leftTab === "description" ? (
          <article>
            <div className="font-mono text-[11px] text-dim">{String(problem.id).padStart(2, "0")} · {problem.slug}</div>
            <h1 className="mt-1 text-xl font-semibold tracking-tight">{problem.title}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-muted">
              <DifficultyTag d={problem.difficulty} />
              <span>time {problem.time_limit_ms}ms</span>
              <span>memory {problem.memory_limit_mb}MB</span>
              <span>{problem.hidden_test_count} hidden tests</span>
              {problem.acceptance_rate !== null && <span>acceptance {problem.acceptance_rate}%</span>}
              {problem.status === "solved" && <span className="text-accent">✓ solved</span>}
            </div>
            <Markdown text={problem.statement} className="mt-5 text-[14px]" />
            <h3 className="label mt-6 mb-2">input</h3>
            <Markdown text={problem.input_spec} className="text-[14px]" />
            <h3 className="label mt-4 mb-2">output</h3>
            <Markdown text={problem.output_spec} className="text-[14px]" />
            {problem.examples.map((ex, i) => (
              <div key={i} className="mt-5">
                <div className="label mb-1.5">example {i + 1}</div>
                <div className="grid gap-px border border-line bg-line sm:grid-cols-2">
                  <div className="bg-panel-2 p-3"><div className="mb-1 font-mono text-[10px] text-dim">stdin</div><pre className="overflow-x-auto font-mono text-[12.5px] text-fg">{ex.input}</pre></div>
                  <div className="bg-panel-2 p-3"><div className="mb-1 font-mono text-[10px] text-dim">stdout</div><pre className="overflow-x-auto font-mono text-[12.5px] text-accent">{ex.output}</pre></div>
                </div>
                {ex.explanation && <p className="mt-1.5 text-[13px] text-muted">{ex.explanation}</p>}
              </div>
            ))}
            <h3 className="label mt-6 mb-2">constraints</h3>
            <ul className="space-y-1 font-mono text-[12.5px] text-muted">
              {problem.constraints.split("\n").map((c) => <li key={c}><span className="text-dim">▪</span> {c}</li>)}
            </ul>
            <div className="mt-6 flex flex-wrap gap-1.5">
              {problem.tags.map((t) => <span key={t.slug} className="border border-line px-1.5 py-0.5 font-mono text-[11px] text-muted">#{t.slug}</span>)}
            </div>
          </article>
        ) : (
          <div>
            {!user && <p className="font-mono text-[12px] text-dim">log in to see your submissions.</p>}
            <ul className="divide-y divide-line border border-line">
              {history.map((s) => (
                <li key={s.id}>
                  <Link href={`/submissions/${s.id}`} className="grid grid-cols-[5rem_1fr_4rem_4.5rem_4.5rem] items-center gap-2 px-3 py-2 font-mono text-[12px] hover:bg-panel-2">
                    <span className="text-dim">{s.display_id}</span>
                    <VerdictBadge verdict={s.verdict} status={s.status} />
                    <span className="text-muted">{s.language}</span>
                    <span className="text-muted">{ms(s.runtime_ms)}</span>
                    <span className="text-dim">{ago(s.created_at)}</span>
                  </Link>
                </li>
              ))}
              {user && history.length === 0 && <li className="px-3 py-6 text-center font-mono text-[12px] text-dim">no submissions yet</li>}
            </ul>
          </div>
        )}
      </div>
    </div>
  );

  const editorPane = (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b border-line bg-panel px-2 py-1.5">
        <select value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Language"
          className="border border-line bg-panel-2 px-2 py-1 font-mono text-[12px] text-fg outline-none focus:border-line-strong">
          {problem.languages.map((l) => <option key={l.key} value={l.key}>{l.display_name} · {l.version}</option>)}
        </select>
        <button onClick={() => { if (language && confirm("Reset to the starter template?")) setCode(language.template); }}
          className="px-2 py-1 font-mono text-[11px] text-dim hover:text-fg" title="Reset to template">reset</button>
        <div className="ml-auto flex items-center gap-2">
          {!user && <Link href={`/login?next=/problems/${slug}`} className="font-mono text-[11px] text-amber">log in to run code →</Link>}
          <button onClick={() => execute("RUN")} disabled={!user || busy}
            className="flex items-center gap-2 border border-line-strong px-3 py-1 font-mono text-[12px] text-fg transition-colors hover:border-muted disabled:opacity-40">
            ▷ run <Kbd>⌘&apos;</Kbd>
          </button>
          <button onClick={() => execute("SUBMIT")} disabled={!user || busy}
            className="flex items-center gap-2 bg-accent px-3 py-1 font-mono text-[12px] font-medium text-bg transition-opacity hover:opacity-90 disabled:opacity-40">
            submit <Kbd>⌘↵</Kbd>
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 bg-[#0a0c0f]">
        <CodeEditor value={code} language={language?.monaco_language ?? "plaintext"} onChange={setCode}
          onRun={() => void execute("RUN")} onSubmit={() => void execute("SUBMIT")} />
      </div>
    </div>
  );

  const consolePane = (
    <div className="flex min-h-0 flex-1 flex-col bg-panel/60">
      <div className="flex items-center gap-1 border-b border-line px-2 font-mono text-[12px]">
        {(["testcase", "execution"] as const).map((t) => (
          <button key={t} onClick={() => setConsoleTab(t)}
            className={`border-b px-3 py-2 transition-colors ${consoleTab === t ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg"}`}>
            {t}
          </button>
        ))}
        {activeId !== null && (
          <span className="ml-auto pr-2 font-mono text-[11px] text-dim">
            {activeMode.toLowerCase()} · <Link className="hover:text-fg" href={`/submissions/${activeId}`}>CF-{activeId}</Link>
          </span>
        )}
      </div>
      <div className="scrollbar-thin min-h-0 flex-1 overflow-auto p-3">
        {error && <div className="mb-3 border border-red/40 bg-red/5 px-3 py-2 font-mono text-[12px] text-red">{error}</div>}
        {consoleTab === "testcase" ? (
          <div className="space-y-3">
            <label className="flex items-center gap-2 font-mono text-[12px] text-muted">
              <input type="checkbox" checked={customOn} onChange={(e) => setCustomOn(e.target.checked)} className="accent-[var(--color-accent)]" />
              run with custom input <span className="text-dim">(otherwise: the {problem.examples.length} sample tests)</span>
            </label>
            {customOn ? (
              <textarea value={customInput} onChange={(e) => setCustomInput(e.target.value)} spellCheck={false} rows={8}
                className="w-full resize-y border border-line bg-panel-2 p-2 font-mono text-[12.5px] text-fg outline-none focus:border-line-strong" />
            ) : (
              <div className="grid gap-2 md:grid-cols-2">
                {problem.examples.map((ex, i) => (
                  <div key={i} className="border border-line bg-panel-2 p-2">
                    <div className="font-mono text-[10px] text-dim">sample {i + 1}</div>
                    <pre className="mt-1 max-h-28 overflow-auto font-mono text-[12px] text-muted">{ex.input}</pre>
                  </div>
                ))}
              </div>
            )}
            <p className="font-mono text-[11px] text-dim">“run” never touches hidden tests. “submit” judges against all {problem.examples.length + problem.hidden_test_count} tests.</p>
          </div>
        ) : activeId === null ? (
          <p className="font-mono text-[12px] text-dim">run or submit to see the execution trace.</p>
        ) : (
          <div className="space-y-3">
            <div className="h-[260px]"><ExecutionVisualizer id={activeId} state={pipeline} /></div>
            {detail && <ResultPanel detail={detail} />}
            {pipeline.done && detail && (
              <div className="font-mono text-[11px] text-dim">
                peak cpu {ms(detail.runtime_ms)} · peak memory {kb(detail.memory_kb)} · {detail.tests_passed ?? 0}/{detail.tests_total ?? 0} passed
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <main className="flex h-[calc(100vh-3rem)] flex-col">
      <Split storageKey="cf:split:main" initial={0.42} min={0.25} max={0.7} a={left}
        b={<Split direction="vertical" storageKey="cf:split:editor" initial={0.58} min={0.25} max={0.85} a={editorPane} b={consolePane} />} />
    </main>
  );
}
