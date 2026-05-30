def test_package_imports() -> None:
    import sc2_agent
    from sc2_agent.config.settings import Settings
    from sc2_agent.runtime.state import RuntimeState

    assert sc2_agent.__version__
    assert Settings().max_agent_iterations > 0
    assert RuntimeState.PAUSED_THINKING.value == "PAUSED_THINKING"
