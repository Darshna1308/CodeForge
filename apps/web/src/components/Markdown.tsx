import { Fragment, type ReactNode } from "react";

/**
 * Deliberately tiny Markdown subset (paragraphs, "- " lists, **bold**, `code`)
 * rendered as React elements — no HTML injection path, so problem text can
 * never become markup.
 */
function inline(text: string, keyBase: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    const key = `${keyBase}-${i}`;
    if (p.startsWith("`") && p.endsWith("`")) return <code key={key}>{p.slice(1, -1)}</code>;
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={key}>{p.slice(2, -2)}</strong>;
    return <Fragment key={key}>{p}</Fragment>;
  });
}

export function Markdown({ text, className = "" }: { text: string; className?: string }) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <div className={`prose-cf ${className}`}>
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (lines.every((l) => l.startsWith("- "))) {
          return <ul key={i}>{lines.map((l, j) => <li key={j}>{inline(l.slice(2), `${i}-${j}`)}</li>)}</ul>;
        }
        return <p key={i}>{lines.flatMap((l, j) => (j ? [<br key={`br${j}`} />, ...inline(l, `${i}-${j}`)] : inline(l, `${i}-${j}`)))}</p>;
      })}
    </div>
  );
}
