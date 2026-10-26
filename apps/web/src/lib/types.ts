export type Difficulty = "EASY" | "MEDIUM" | "HARD";
export type SubmissionStatus =
  | "CREATED" | "QUEUED" | "PROCESSING" | "COMPILING" | "RUNNING" | "JUDGING"
  | "COMPLETED" | "INTERNAL_ERROR" | "CANCELLED";
export type Verdict =
  | "ACCEPTED" | "WRONG_ANSWER" | "COMPILATION_ERROR" | "RUNTIME_ERROR" | "TIME_LIMIT_EXCEEDED"
  | "MEMORY_LIMIT_EXCEEDED" | "OUTPUT_LIMIT_EXCEEDED" | "EXECUTED";
export type TestVerdict = Exclude<Verdict, "COMPILATION_ERROR"> | "SKIPPED";

export interface User { id: number; username: string; email?: string | null; role: string; created_at: string }
export interface Tag { slug: string; name: string; count?: number | null }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }

export interface ProblemSummary {
  id: number; slug: string; title: string; difficulty: Difficulty; tags: Tag[];
  accepted: number; submissions: number; acceptance_rate: number | null; status: "solved" | "attempted" | null;
}
export interface Language { key: string; display_name: string; version: string; monaco_language: string; template: string }
export interface ProblemDetail extends Omit<ProblemSummary, "status"> {
  statement: string; input_spec: string; output_spec: string; constraints: string;
  time_limit_ms: number; memory_limit_mb: number; examples: { input: string; output: string; explanation: string | null }[];
  hidden_test_count: number; languages: Language[]; status: "solved" | "attempted" | null;
}

export interface TestResult {
  ordinal: number; verdict: TestVerdict; is_sample: boolean; cpu_ms: number | null; wall_ms: number | null;
  memory_kb: number | null; exit_code: number | null; signal: number | null;
  input?: string | null; expected_output?: string | null; stdout?: string | null; stderr?: string | null;
}
export interface SubmissionSummary {
  id: number; display_id: string; problem_slug: string; problem_title: string; language: string;
  mode: "SUBMIT" | "RUN"; status: SubmissionStatus; verdict: Verdict | null; runtime_ms: number | null;
  memory_kb: number | null; tests_passed: number | null; tests_total: number | null; attempt: number;
  created_at: string; finished_at: string | null;
}
export interface Attempt {
  attempt_no: number; worker_id: string; outcome: string; started_at: string; finished_at: string | null;
  queue_wait_ms: number | null; sandbox_start_ms: number | null; compile_ms: number | null; total_ms: number | null; error: string | null;
}
export interface SubmissionDetail extends SubmissionSummary {
  source_code?: string; custom_input?: string | null; compile_output: string | null; compile_ms: number | null;
  error_message: string | null; worker_id: string | null; queued_at: string | null; started_at: string | null;
  results: TestResult[]; attempts: Attempt[];
  transitions?: { from_status: SubmissionStatus | null; to_status: SubmissionStatus; attempt: number; actor: string; at: string }[];
}
export interface Accepted { id: number; display_id: string; status: SubmissionStatus; mode: string; events_url: string }

/** One event from GET /submissions/{id}/events (SSE). */
export interface PipelineEvent {
  type: string;
  ts?: number;
  [k: string]: unknown;
}
