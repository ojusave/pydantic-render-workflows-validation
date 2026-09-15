from app import app


def test_agent_operations_register_as_workflow_tasks() -> None:
    task_names = set(app._registry.get_task_names())

    assert "run_research" in task_names
    assert "researcher__model.request" in task_names
    # `delegate_task` is registered as this toolset's call_tool task.
    assert any("sub_agents.call_tool" in name for name in task_names)
