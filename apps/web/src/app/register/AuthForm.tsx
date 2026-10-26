"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import type { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(username, password);
      else await register(username, email, password);
      // Only same-site relative paths are followed (no open redirect).
      router.push(next && next.startsWith("/") && !next.startsWith("//") ? next : "/problems");
    } catch (err) {
      const e2 = err as ApiError;
      const fieldMsg = Array.isArray(e2.details) ? (e2.details as { loc: string[]; msg: string }[]).map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ") : null;
      setError(fieldMsg || e2.message);
    } finally {
      setBusy(false);
    }
  };

  const field = "h-10 w-full border border-line bg-panel-2 px-3 font-mono text-[13px] text-fg outline-none transition-colors focus:border-accent/60";
  return (
    <main className="mx-auto flex max-w-md flex-col px-4 py-16">
      <div className="font-mono text-[11px] text-dim"><span className="text-accent">$</span> codeforge auth {mode}</div>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">{mode === "login" ? "Log in" : "Create an account"}</h1>
      <form onSubmit={submit} className="mt-6 space-y-3 border border-line bg-panel p-5">
        <label className="block">
          <span className="label">{mode === "login" ? "username or email" : "username"}</span>
          <input className={`${field} mt-1`} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
        </label>
        {mode === "register" && (
          <label className="block">
            <span className="label">email</span>
            <input className={`${field} mt-1`} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
          </label>
        )}
        <label className="block">
          <span className="label">password {mode === "register" && <span className="normal-case tracking-normal text-dim">(min 8 chars)</span>}</span>
          <input className={`${field} mt-1`} type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "register" ? 8 : 1} required />
        </label>
        {error && <p className="font-mono text-[12px] text-red" role="alert">{error}</p>}
        <button disabled={busy} className="h-10 w-full bg-accent font-mono text-[13px] font-medium text-bg transition-opacity hover:opacity-90 disabled:opacity-50">
          {busy ? "…" : mode === "login" ? "log in" : "create account"}
        </button>
      </form>
      <p className="mt-4 font-mono text-[12px] text-muted">
        {mode === "login" ? <>no account? <Link href="/register" className="text-accent">register</Link></> : <>have an account? <Link href="/login" className="text-accent">log in</Link></>}
      </p>
      <p className="mt-6 font-mono text-[11px] leading-relaxed text-dim">
        passwords are hashed with argon2id · sessions are signed JWTs in an httpOnly SameSite=Lax cookie · logout revokes the token server-side
      </p>
    </main>
  );
}
