import { ChildRun, RunState } from "./api";

interface ExecutionViewProps {
  children: ChildRun[];
  state: RunState;
}

interface TaskPresentation {
  label: string;
  detail: string;
  kind: "model" | "branch" | "search" | "fetch" | "support";
}

function presentTask(name: string): TaskPresentation {
  if (name.includes("sub_agents.call_tool")) {
    return {
      label: "Delegated researcher branch",
      detail: "Pydantic AI split off a focused sub-question.",
      kind: "branch",
    };
  }
  if (name.includes("web_search.call_tool")) {
    return {
      label: "Search the web",
      detail: "A researcher searched for relevant sources.",
      kind: "search",
    };
  }
  if (name.includes("web_fetch.call_tool")) {
    return {
      label: "Read a source",
      detail: "A researcher fetched a page to inspect its contents.",
      kind: "fetch",
    };
  }
  if (name.endsWith("__model.request")) {
    return {
      label: "Ask the model",
      detail: "Pydantic AI asked the model what to do or to synthesize findings.",
      kind: "model",
    };
  }
  if (name.includes("compact_messages") || name.includes("summarize")) {
    return {
      label: "Manage context",
      detail: "The harness kept the agent context within its output limits.",
      kind: "support",
    };
  }
  return {
    label: "Harness operation",
    detail: "Supporting validation or tool execution managed by the harness.",
    kind: "support",
  };
}

function count(children: ChildRun[], fragment: string): number {
  return children.filter((child) => child.task_name.includes(fragment)).length;
}

export function ExecutionView({ children, state }: ExecutionViewProps) {
  const visible = children.filter((child) => {
    const name = child.task_name;
    return (
      name.endsWith("__model.request") ||
      name.includes(".call_tool") ||
      name.includes("compact_messages") ||
      name.includes(".summarize")
    );
  });
  const branches = count(children, "sub_agents.call_tool");
  const searches = count(children, "web_search.call_tool");
  const fetches = count(children, "web_fetch.call_tool");
  const modelCalls = children.filter((child) =>
    child.task_name.endsWith("__model.request"),
  ).length;

  return (
    <section className="execution" aria-labelledby="execution-title">
      <div className="execution-heading">
        <div>
          <p className="section-kicker">LIVE EXECUTION</p>
          <h2 id="execution-title">How this research runs</h2>
        </div>
        <span className={`state-pill state-${state}`}>{state}</span>
      </div>

      <ol className="system-flow">
        <li>
          <strong>Pydantic AI decides</strong>
          <span>The agent chooses when to delegate, search, fetch, and answer.</span>
        </li>
        <li>
          <strong>The harness translates</strong>
          <span>Each model or tool operation becomes a durable task.</span>
        </li>
        <li>
          <strong>Render Workflows executes</strong>
          <span>Render supplies compute, retries, timeouts, and run history.</span>
        </li>
      </ol>

      <div className="execution-stats">
        <div><strong>{branches}</strong><span>research branches</span></div>
        <div><strong>{modelCalls}</strong><span>model calls</span></div>
        <div><strong>{searches}</strong><span>web searches</span></div>
        <div><strong>{fetches}</strong><span>source fetches</span></div>
      </div>

      {children.length === 0 ? (
        <p className="execution-empty">
          The parent task is starting. Delegated branches and tools will appear here.
        </p>
      ) : (
        <div className="task-tree">
          <div className="task-row task-root">
            <span className="task-marker">1</span>
            <div>
              <strong>Parent researcher</strong>
              <p>Pydantic AI plans the research and combines the final answer.</p>
            </div>
          </div>
          {visible.map((child, index) => {
            const task = presentTask(child.task_name);
            return (
              <div
                className={`task-row task-${task.kind}`}
                key={child.task_run_id}
                style={{ marginLeft: `${Math.min(child.depth, 4) * 1.1}rem` }}
              >
                <span className="task-marker">{index + 2}</span>
                <div>
                  <strong>{task.label}</strong>
                  <p>{task.detail}</p>
                </div>
                <span className="task-status">{child.status}</span>
              </div>
            );
          })}
        </div>
      )}

      <details className="technical-details">
        <summary>Technical details: {children.length} Render child tasks</summary>
        <ul>
          {children.map((child) => (
            <li key={`detail-${child.task_run_id}`}>
              <span>{child.status}</span>
              <code>{child.task_name}</code>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
