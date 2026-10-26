"use client";

import { useEffect, useReducer, useRef } from "react";

import { api, API_URL } from "./api";
import { applyEvent, fromSnapshot, initialPipeline, type PipelineState } from "./pipeline";
import type { PipelineEvent, SubmissionDetail } from "./types";

const EVENT_TYPES = [
  "queued", "claimed", "sandbox_ready", "compiling", "compiled", "status", "running", "test",
  "judging", "completed", "retrying", "internal_error", "cancelled",
];

type Action = { kind: "reset" } | { kind: "event"; event: PipelineEvent } | { kind: "snapshot"; detail: SubmissionDetail };

function reducer(state: PipelineState, action: Action): PipelineState {
  if (action.kind === "reset") return initialPipeline();
  if (action.kind === "snapshot") return fromSnapshot(state, action.detail);
  return applyEvent(state, action.event);
}

/**
 * Subscribes to the submission's SSE stream. EventSource reconnects on its own
 * and sends Last-Event-ID so the server resumes the Redis Stream where we left
 * off. If the stream cannot be established at all, falls back to polling.
 */
export function useSubmissionStream(id: number | null, onDone?: (detail: SubmissionDetail | null) => void): PipelineState {
  const [state, dispatch] = useReducer(reducer, undefined, initialPipeline);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useEffect(() => {
    dispatch({ kind: "reset" });
    if (id === null) return;
    let closed = false;
    let poll: ReturnType<typeof setInterval> | null = null;
    let finished = false;

    const finish = async () => {
      if (finished) return;
      finished = true;
      try {
        const detail = await api<SubmissionDetail>(`/submissions/${id}`);
        if (!closed) dispatch({ kind: "snapshot", detail });
        doneRef.current?.(detail);
      } catch {
        doneRef.current?.(null);
      }
    };

    const es = new EventSource(`${API_URL}/submissions/${id}/events`, { withCredentials: true });
    es.addEventListener("snapshot", (m) => {
      const detail = JSON.parse((m as MessageEvent).data) as SubmissionDetail;
      dispatch({ kind: "snapshot", detail });
    });
    for (const t of EVENT_TYPES) {
      es.addEventListener(t, (m) => dispatch({ kind: "event", event: JSON.parse((m as MessageEvent).data) }));
    }
    es.addEventListener("end", () => {
      es.close();
      void finish();
    });
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED && !finished && !poll) {
        // Could not (re)connect: degrade to polling the REST endpoint.
        poll = setInterval(async () => {
          try {
            const detail = await api<SubmissionDetail>(`/submissions/${id}`);
            dispatch({ kind: "snapshot", detail });
            if (["COMPLETED", "INTERNAL_ERROR", "CANCELLED"].includes(detail.status)) {
              if (poll) clearInterval(poll);
              void finish();
            }
          } catch {
            /* keep polling */
          }
        }, 1000);
      }
    };
    return () => {
      closed = true;
      es.close();
      if (poll) clearInterval(poll);
    };
  }, [id]);

  return state;
}
