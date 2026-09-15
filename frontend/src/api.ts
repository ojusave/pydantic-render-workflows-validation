export type RunState = "running" | "completed" | "failed";

export interface StartData {
  task_run_id: string;
}

export interface ChildRun {
  task_run_id: string;
  task_id: string;
  task_name: string;
  parent_task_run_id: string;
  depth: number;
  status: string;
}

export interface RunData {
  task_run_id: string;
  state: RunState;
  response: string | null;
  model: string | null;
  children: ChildRun[];
}

export interface StatusData {
  submissions_enabled: boolean;
}

export interface ApiError {
  code: string;
  message: string;
}

interface Envelope<T> {
  data: T | null;
  error: ApiError | null;
  meta: Record<string, string>;
}

async function unwrap<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as Envelope<T>;
  if (!response.ok || payload.error || !payload.data) {
    throw new Error(payload.error?.message ?? "The research request failed.");
  }
  return payload.data;
}

/** Whether the API is accepting new research submissions. */
export async function readStatus(): Promise<StatusData> {
  return unwrap<StatusData>(await fetch("/api/status"));
}

/** Submit a prompt and return its Render task run ID. */
export async function startRun(message: string): Promise<StartData> {
  return unwrap<StartData>(
    await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }),
  );
}

/** Read the current state of a submitted run. */
export async function readRun(taskRunId: string): Promise<RunData> {
  return unwrap<RunData>(await fetch(`/api/runs/${taskRunId}`));
}
