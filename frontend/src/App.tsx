import { FormEvent, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Footer,
  Label,
  Navigation,
  RenderLogo,
  Textarea,
} from "render-dds";

import { RunData, readRun, readStatus, startRun } from "./api";
import { links } from "./links";

const POLL_INTERVAL_MS = 1500;

export default function App() {
  const [prompt, setPrompt] = useState("");
  const [run, setRun] = useState<RunData | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [submissionsEnabled, setSubmissionsEnabled] = useState(true);
  const startedAt = useRef<number>(0);

  const watching = runId !== null && run?.state !== "completed";

  useEffect(() => {
    let cancelled = false;
    void readStatus()
      .then((status) => {
        if (!cancelled) {
          setSubmissionsEnabled(status.submissions_enabled);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSubmissionsEnabled(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!watching || runId === null) {
      return;
    }

    let cancelled = false;
    let timer = 0;
    const tick = async () => {
      try {
        const next = await readRun(runId);
        if (cancelled) {
          return;
        }
        setRun(next);
        setElapsed(Math.round((Date.now() - startedAt.current) / 1000));
        if (next.state !== "completed") {
          timer = window.setTimeout(tick, POLL_INTERVAL_MS);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(
            caught instanceof Error ? caught.message : "The research run failed.",
          );
          setRunId(null);
        }
      }
    };

    timer = window.setTimeout(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [runId, watching]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = prompt.trim();
    if (!message) {
      setError("Enter a research question first.");
      return;
    }

    setError(null);
    setRun(null);
    setRunId(null);
    setElapsed(0);
    startedAt.current = Date.now();
    try {
      const started = await startRun(message);
      setRunId(started.task_run_id);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "The research request failed.",
      );
    }
  }

  const children = run?.children ?? [];

  return (
    <div className="page-shell">
      <Navigation
        logo={<RenderLogo variant="full" height={26} />}
        actions={
          <div className="header-actions">
            <a className="chrome-link chrome-link-secondary" href={links.deploy}>
              Deploy
            </a>
            <a className="chrome-link" href={links.signup}>
              Sign up
            </a>
          </div>
        }
      />

      <main>
        <section className="hero">
          <p className="eyebrow">PYDANTIC AI HARNESS × RENDER WORKFLOWS</p>
          <h1>Run the harness researcher as Workflow tasks</h1>
          <p>
            The parent agent can search, fetch, and delegate focused
            sub-questions. Each model request and each research branch runs as
            its own Render task, with its own timeout, retries, and compute.
          </p>
        </section>

        <Card className="prompt-card">
          <CardHeader>
            <CardTitle>Ask a research question</CardTitle>
            <CardDescription>
              Submitting returns a task run ID immediately. Polling lists the
              child tasks Render spawned for this run.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!submissionsEnabled && (
              <Alert variant="info" title="Submissions disabled">
                Set a real <code>PYDANTIC_AI_MODEL</code> and provider key on
                the Workflow, then enable <code>WORKFLOWS_ENABLED</code> on the
                web service. TestModel cannot produce research answers.
              </Alert>
            )}
            <form onSubmit={handleSubmit}>
              <div className="field">
                <Label htmlFor="prompt">Question</Label>
                <Textarea
                  id="prompt"
                  rows={5}
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder="Compare Render Workflows and Temporal for long-running AI research."
                  disabled={watching || !submissionsEnabled}
                  error={Boolean(error)}
                />
              </div>
              <Button type="submit" disabled={watching || !submissionsEnabled}>
                {watching ? "Research running…" : "Run research"}
              </Button>
            </form>

            <div className="result-region" aria-live="polite">
              {error && (
                <Alert variant="error" title="Request failed">
                  {error}
                </Alert>
              )}
              {watching && (
                <Alert variant="info" title="Workflow running">
                  Render is executing the researcher and any delegated
                  branches. Elapsed: {elapsed}s
                  {runId && <p className="run-id">Task run: {runId}</p>}
                </Alert>
              )}
              {children.length > 0 && (
                <ul className="child-runs">
                  {children.map((child) => (
                    <li key={child.task_run_id}>
                      <span className="child-status">{child.status}</span>
                      <code>{child.task_id}</code>
                      <span className="run-id">{child.task_run_id}</span>
                    </li>
                  ))}
                </ul>
              )}
              {run?.state === "completed" && (
                <Alert variant="success" title="Research response">
                  <p className="response">{run.response}</p>
                  {run.model?.includes("TestModel") && (
                    <p className="model-note">
                      This run used TestModel, which echoes tool results
                      instead of researching. Set{" "}
                      <code>PYDANTIC_AI_MODEL</code> on the Workflow for a real
                      provider.
                    </p>
                  )}
                  <p className="run-id">
                    Task run: {run.task_run_id}
                    {run.model ? ` · Model: ${run.model}` : ""}
                    {elapsed ? ` · ${elapsed}s` : ""}
                  </p>
                </Alert>
              )}
            </div>
          </CardContent>
        </Card>
      </main>

      <Footer
        centered
        copyright="Pydantic AI Researcher on Render Workflows"
        links={[
          { label: "GitHub repository", href: links.github },
          { label: "Workflows docs", href: links.workflowsDocs },
        ]}
      />
    </div>
  );
}
