from __future__ import annotations

import pytest
from src.agents.external_workflow_registry import ExternalWorkflowRegistry
from src.agents.framework_adapter import AgentFrameworkAdapterRegistry


def test_framework_registry_contains_external_frameworks():
    registry = AgentFrameworkAdapterRegistry().build_registry()
    assert 'native-python' in registry
    assert 'langgraph-compatible' in registry
    assert 'dify-compatible' in registry
    assert 'ray-compatible' in registry
    assert registry['langgraph-compatible']['status'] == 'integrated'
    assert registry['langgraph-compatible']['runtime_status'] in {'active', 'installed', 'fallback'}
    assert registry['langgraph-compatible']['diagnostics']['detection_method'] == 'importlib.util.find_spec'
    assert 'snapshot' in registry['langgraph-compatible']['supports']


@pytest.mark.asyncio
async def test_framework_registry_can_register_and_invoke_framework_adapter():
    adapter = AgentFrameworkAdapterRegistry()

    async def _fake_invoker(**kwargs):
        return {'framework': 'langgraph-compatible', 'input': kwargs.get('input_data')}

    adapter.register_invoker('langgraph-compatible', _fake_invoker)
    result = await adapter.invoke('langgraph-compatible', input_data={'query': '蓝牙耳机'})
    detail = adapter.get_framework('langgraph-compatible')
    assert result['framework'] == 'langgraph-compatible'
    assert result['input']['query'] == '蓝牙耳机'
    assert detail['invoker_registered'] is True


@pytest.mark.asyncio
async def test_workflow_registry_maps_and_executes_selection_workflow():
    registry = ExternalWorkflowRegistry()
    workflow = registry.build_registry()['selection_workflow']
    assert workflow['active_framework'] == 'langgraph-compatible'
    assert workflow['fallback_framework'] == 'native-python'

    result = await registry.execute_workflow(
        'selection_workflow',
        input_data={'query': '蓝牙耳机', 'category': 'electronics', 'target_market': 'US'},
        breakpoints=['risk_assessment'],
        single_step=True,
    )
    assert result['snapshot']['framework'] == 'langgraph-compatible'
    assert result['single_step'] is True
    assert result['executed_node'] == 'data_collection'
