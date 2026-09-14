from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai_harness import RenderWorkflows
from render import TaskContext, Workflows


async def lookup(query: str) -> str:
    return f"found:{query}"


app = Workflows()
render_workflows = RenderWorkflows(app)
agent = Agent(
    TestModel(call_tools=["lookup"]),
    name="support",
    tools=[lookup],
    capabilities=[render_workflows],
)


@render_workflows.task(name="run_agent")
async def run_agent(ctx: TaskContext, prompt: str) -> str:
    del ctx
    return (await agent.run(prompt)).output


if __name__ == "__main__":
    app.start()
