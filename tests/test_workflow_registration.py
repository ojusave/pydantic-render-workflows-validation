from app import app


def test_agent_operations_register_as_workflow_tasks() -> None:
    task_names = set(app._registry.get_task_names())

    assert "run_research" in task_names
    assert "researcher__model.request" in task_names
    # The delegate registers its own operations under its own prefix.
    assert "sub_researcher__model.request" in task_names
    assert "sub_researcher__function_toolset__web_search.call_tool" in task_names
    # Inline placement is explicit; shared task definitions remain registered.
    assert "researcher__function_toolset__sub_agents.call_tool" in task_names
