"use client";

import Editor, { loader, type OnMount } from "@monaco-editor/react";
import { useRef } from "react";

// Monaco's AMD build is served from /public (copied at install time): no CDN.
loader.config({ paths: { vs: "/monaco/vs" } });

export function CodeEditor({
  value, language, onChange, onRun, onSubmit,
}: {
  value: string; language: string; onChange: (v: string) => void; onRun: () => void; onSubmit: () => void;
}) {
  const handlers = useRef({ onRun, onSubmit });
  handlers.current = { onRun, onSubmit };

  const mount: OnMount = (editor, monaco) => {
    monaco.editor.defineTheme("codeforge", {
      base: "vs-dark",
      inherit: true,
      rules: [
        { token: "comment", foreground: "5a636f", fontStyle: "italic" },
        { token: "keyword", foreground: "b69cff" },
        { token: "string", foreground: "4ff0a0" },
        { token: "number", foreground: "f4b74a" },
        { token: "type", foreground: "6cb6ff" },
      ],
      colors: {
        "editor.background": "#0a0c0f",
        "editor.lineHighlightBackground": "#11141980",
        "editorLineNumber.foreground": "#3a424d",
        "editorLineNumber.activeForeground": "#8b95a3",
        "editorCursor.foreground": "#4ff0a0",
        "editor.selectionBackground": "#4ff0a033",
        "editorIndentGuide.background1": "#1c2128",
        "editorGutter.background": "#0a0c0f",
      },
    });
    monaco.editor.setTheme("codeforge");
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Quote, () => handlers.current.onRun());
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => handlers.current.onSubmit());
    editor.focus();
  };

  return (
    <Editor
      value={value}
      language={language}
      onChange={(v) => onChange(v ?? "")}
      onMount={mount}
      theme="vs-dark"
      loading={<div className="p-4 font-mono text-xs text-dim">loading editor…</div>}
      options={{
        fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
        fontSize: 13.5,
        lineHeight: 21,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        smoothScrolling: true,
        cursorBlinking: "smooth",
        renderLineHighlight: "line",
        padding: { top: 12 },
        tabSize: 4,
        automaticLayout: true,
        scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
      }}
    />
  );
}
