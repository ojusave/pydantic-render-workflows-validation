import os

from pydantic_ai import Agent
from pydantic_ai.capabilities import WebFetch, WebSearch
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel
from pydantic_ai_harness import RenderWorkflows, SubAgent, SubAgents, ToolOutputLimits
from render import Options, Retry, TaskContext, Workflows

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
        lookup = {tool.name: tool for tool in tools if visibility(tool.name) != "withheld"}
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
        capabilities=[
            WebSearch(local=True, native=False),
            WebFetch(local=True, native=False),
            ToolOutputLimits(),
        ],
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
        SubAgents(agents=[sub_researcher], agent_folders=None),
        ToolOutputLimits(),
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
