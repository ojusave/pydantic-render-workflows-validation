import os

from pydantic_ai import Agent
from pydantic_ai.capabilities import WebFetch, WebSearch
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel
from pydantic_ai_harness import RenderWorkflows, SubAgent, SubAgents, ToolOutputLimits
from pydantic_ai_harness.subagents._toolset import SubAgentToolset
from render import Options, Retry, TaskContext, Workflows


def _ensure_toolset_id(toolset: object, toolset_id: str) -> object:
    """Render Workflows requires a unique id on every leaf FunctionToolset."""
    if toolset is not None and getattr(toolset, "_id", None) is None:
        toolset._id = toolset_id
    return toolset


class WorkflowSubAgents(SubAgents):  # type: ignore[type-arg]
    """Copy SubAgents' capability id onto the leaf FunctionToolset Render requires."""

    def get_toolset(self):
        return _ensure_toolset_id(super().get_toolset(), self.id or "sub_agents")


class WorkflowToolOutputLimits(ToolOutputLimits):  # type: ignore[type-arg]
    """Copy ToolOutputLimits' capability id onto its read_tool_result toolset."""

    def get_toolset(self):
        return _ensure_toolset_id(super().get_toolset(), self.id or "tool_output_limits")


_orig_run_delegation = SubAgentToolset._run_delegation


async def _run_delegation_with_model(
    self: object,
    ctx: object,
    agent_name: str,
    sub_agent: object,
    *,
    task: str,
    key: str | None,
) -> str:
    """Supply `model` on Render child-task contexts so SubAgents can inherit it."""

    class _CtxWithModel:
        def __init__(self, inner: object, model: object) -> None:
            object.__setattr__(self, "_inner", inner)
            object.__setattr__(self, "model", model)

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

    agent = getattr(sub_agent, "agent", None)
    model = getattr(agent, "model", None) or MODEL
    wrapped = _CtxWithModel(ctx, model)
    return await _orig_run_delegation(
        self, wrapped, agent_name, sub_agent, task=task, key=key
    )


SubAgentToolset._run_delegation = _run_delegation_with_model

# Keep these blocks in sync with pydantic-ai-harness/examples/research_agent.py.
INSTRUCTIONS = """\
Search broadly before drawing conclusions.
Read the sources that support each important claim.
Prefer primary and authoritative sources.
Cite every factual claim with a direct source link.
Distinguish sourced facts from your own inference.
"""

DEFAULT_MODEL = os.environ.get("PYDANTIC_AI_MODEL")


class DelegateTestModel(TestModel):
    """TestModel that delegates once, then answers as the child researcher."""

    def gen_tool_args(self, tool_def: object) -> object:
        name = getattr(tool_def, "name", None)
        if name == "delegate_task":
            return {"agent_name": "researcher", "task": "Research the user question."}
        return super().gen_tool_args(tool_def)  # type: ignore[arg-type]

    def _get_tool_calls(self, model_request_parameters: object) -> list:
        tools = getattr(model_request_parameters, "function_tools", [])
        visibility = getattr(model_request_parameters, "visibility_of", lambda _name: "visible")
        lookup = {
            tool.name: tool
            for tool in tools
            if visibility(tool.name) != "withheld"
        }
        if "delegate_task" in lookup:
            return [("delegate_task", lookup["delegate_task"])]
        return []


def resolve_model() -> Model | str:
    """Use a real provider when PYDANTIC_AI_MODEL is set, otherwise TestModel.

    Tests and local smoke runs stay keyless. The UI is not a research product
    until a real model is configured on the Workflow.
    """
    if DEFAULT_MODEL:
        return DEFAULT_MODEL
    return DelegateTestModel()


MODEL = resolve_model()
MODEL_LABEL = DEFAULT_MODEL or "pydantic-ai TestModel"

MODEL_OPTIONS = Options(
    retry=Retry(max_retries=2, wait_duration_ms=2_000, backoff_scaling=2),
    timeout_seconds=120,
    plan="starter",
)
# Render fixes tool-task Options at bind time. One tool plan covers
# delegate_task plus local search/fetch; do not vary them per call.
TOOL_OPTIONS = Options(
    retry=Retry(max_retries=1, wait_duration_ms=5_000),
    timeout_seconds=300,
    plan="standard",
)


app = Workflows()
render_workflows = RenderWorkflows(
    app,
    name="researcher",
    model_options=MODEL_OPTIONS,
    tool_options=TOOL_OPTIONS,
)

sub_researcher = SubAgent(
    Agent(
        MODEL,
        name="researcher",
        description=(
            "Research a focused sub-question on the web and report back with findings and source links"
        ),
        # native=False keeps DuckDuckGo/markdownify tools; TestModel cannot
        # take provider-native search/fetch.
        capabilities=[WebSearch(local=True, native=False), WebFetch(local=True, native=False), ToolOutputLimits()],
    ),
    timeout_seconds=240,
    contain_errors=True,
)

agent = Agent(
    MODEL,
    name="researcher",
    instructions=INSTRUCTIONS,
    capabilities=[
        WebSearch(local=True, native=False, id="web_search"),
        WebFetch(local=True, native=False, id="web_fetch"),
        WorkflowSubAgents(agents=[sub_researcher], agent_folders=None),
        WorkflowToolOutputLimits(),
        render_workflows,
    ],
)


@render_workflows.task(name="run_research", timeout_seconds=1800, plan="standard")
async def run_research(ctx: TaskContext, prompt: str) -> dict[str, str]:
    """Run one research prompt through the parent agent."""
    del ctx
    result = await agent.run(prompt, model_settings={"timeout": 60.0})
    return {"answer": result.output, "model": MODEL_LABEL}


if __name__ == "__main__":
    app.start()
