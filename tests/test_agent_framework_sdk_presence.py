from __future__ import annotations

import importlib.util

from src.agents.framework_adapter import AgentFrameworkAdapterRegistry


def test_framework_registry_reports_installed_sdks_when_available():
    registry = AgentFrameworkAdapterRegistry().build_registry()

    assert registry['langgraph-compatible']['package_installed'] is True
    assert registry['langgraph-compatible']['sdk_backed'] is True
    assert registry['langchain-compatible']['package_installed'] is True
    assert registry['langchain-compatible']['sdk_backed'] is True
    assert registry['crewai-compatible']['package_installed'] is True
    assert registry['crewai-compatible']['sdk_backed'] is True

    expected_autogen = bool(importlib.util.find_spec('autogen') or importlib.util.find_spec('autogen_agentchat'))
    assert expected_autogen is True
    assert registry['autogen-compatible']['runtime_status'] in {'installed', 'fallback', 'active'}
