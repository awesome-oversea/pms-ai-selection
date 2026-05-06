from __future__ import annotations

import pytest
from src.agents.data_collection import DataCollectionAgent
from src.services.agent_platform_service import AgentPlatformService
from src.services.dify_workflow_service import DifyWorkflowError


class _FakeSelectionService:
    async def list_tasks(self, status=None, limit=200, offset=0):
        return {
            'total': 3,
            'tasks': [
                {
                    'task_id': 'task-1',
                    'status': 'running',
                    'status_reason': '任务执行中',
                    'retry_count': 0,
                    'manual_interventions': [],
                },
                {
                    'task_id': 'task-2',
                    'status': 'failed',
                    'status_reason': '执行失败',
                    'retry_count': 2,
                    'manual_interventions': [],
                },
                {
                    'task_id': 'task-3',
                    'status': 'dead_letter',
                    'status_reason': '执行超时',
                    'retry_count': 3,
                    'dead_letter': True,
                    'manual_interventions': [
                        {'action': 'resume', 'comment': '人工恢复', 'operator': 'tester'}
                    ],
                },
            ],
        }

    async def list_dead_letter_tasks(self, limit=50, offset=0):
        return {
            'total': 1,
            'tasks': [
                {
                    'task_id': 'task-3',
                    'status': 'dead_letter',
                    'dead_letter': True,
                    'status_reason': '执行超时',
                    'retry_count': 3,
                }
            ],
        }


class _FakeConfigService:
    async def get_config(self, key):
        return {'version': 2, 'value': {'route': 'gray'}}


@pytest.mark.asyncio
async def test_agent_platform_operations_status_contains_diagnostics(monkeypatch):
    service = AgentPlatformService(session=None, tenant_id='tenant-1', actor={'username': 'tester'})
    service.selection_service = _FakeSelectionService()
    service.config_service = _FakeConfigService()

    async def _fake_call_tool(self, tool_name: str, **kwargs):
        if tool_name == "amazon_bsr":
            return {
                "source": "amazon_bsr",
                "mode": "real",
                "products": [{"asin": "B0001"}],
                "total_results": 1,
                "signal_context": {"provider": "external_signal_service", "source_name": "amazon", "source_channel": "public_web_signal"},
                "signal_readiness": {"local_business_ready": True, "enterprise_ready": False, "readiness_tier": "local_business_ready"},
            }
        if tool_name == "google_trends":
            return {
                "source": "google_trends",
                "mode": "real",
                "trend_data": {"bluetooth earbuds": {"avg_interest": 75}},
                "signal_context": {"provider": "external_signal_service", "source_name": "google_trends", "source_channel": "public_web_signal"},
                "signal_readiness": {"local_business_ready": True, "enterprise_ready": False, "readiness_tier": "local_business_ready"},
            }
        if tool_name == "ali1688_supply":
            return {
                "source": "ali1688",
                "mode": "real",
                "suppliers": [{"supplier_id": "SUP-1"}],
                "total_suppliers": 1,
                "signal_context": {"provider": "external_signal_service", "source_name": "ali1688", "source_channel": "public_web_signal"},
                "signal_readiness": {"local_business_ready": True, "enterprise_ready": False, "readiness_tier": "local_business_ready"},
            }
        if tool_name == "tiktok_products":
            return {
                "source": "tiktok_products",
                "mode": "real",
                "products": [{"product_id": "TK-1"}],
                "total_results": 1,
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    class _FakeCollected:
        def __init__(self, output: dict):
            self._output = output

        def to_dict(self) -> dict:
            return {"output": self._output}

    async def _fake_run(self, input_data: dict):
        return _FakeCollected(
            {
                "amazon_data": await _fake_call_tool(self, "amazon_bsr", mode=input_data.get("mode")),
                "tiktok_data": await _fake_call_tool(self, "tiktok_products", mode=input_data.get("mode")),
                "trend_data": await _fake_call_tool(self, "google_trends", mode=input_data.get("mode")),
                "supply_chain_data": await _fake_call_tool(self, "ali1688_supply", mode=input_data.get("mode")),
                "external_signal_summary": {
                    "has_external_signal_fallbacks": True,
                    "fallback_tool_count": 3,
                    "fallback_business_sources": ["amazon", "google_trends", "ali1688"],
                    "local_validation_only_sources": ["amazon", "google_trends", "ali1688"],
                },
            }
        )

    monkeypatch.setattr(DataCollectionAgent, "call_tool", _fake_call_tool)
    monkeypatch.setattr(DataCollectionAgent, "run", _fake_run)

    topology = await service.build_topology()
    assert 'frameworks' in topology
    assert 'state_graph' in topology
    assert 'rag_runtime' in topology
    assert topology['frameworks']['dify-compatible']['dify_runtime']['runtime_status'] == 'compatible-only'
    assert topology['rag_runtime']['vector_backend'] in {'qdrant', 'embedding-memory'}
    assert 'langgraph-compatible' in topology['framework_invokers']
    assert topology['workflow_registry']['selection_workflow']['active_framework'] == 'langgraph-compatible'
    assert topology['message_bus']['backend'] == 'kafka-compatible-local-persistence'
    assert topology['framework_runtime_summary']['runtime_status_breakdown']
    assert topology['message_bus']['trace_summary']['trace_ready'] is True
    assert topology['kafka_compatibility']['mode'] == 'kafka-compatible-local-persistence'
    assert topology['kafka_compatibility']['local_acceptance_ready'] is True
    assert topology['kafka_compatibility']['real_broker_status'] == 'blocked'
    assert topology['message_bus']['kafka_compatibility']['ordered_offset_ready'] is True

    created = await service.create_agent_instance(agent_name='market_insight', config={'priority': 'high'})
    assert created['agent_name'] == 'market_insight'
    assert created['status'] == 'pending'
    listed = await service.list_agent_instances()
    assert listed['total'] >= 1
    fetched = await service.get_agent_instance(created['instance_id'])
    assert fetched is not None
    updated = await service.update_agent_instance_status(created['instance_id'], status='running')
    assert updated is not None
    assert updated['status'] == 'running'
    failed = await service.update_agent_instance_status(created['instance_id'], status='failed')
    assert failed is not None
    assert failed['auto_restart_suggested'] is True
    restarted = await service.restart_agent_instance(created['instance_id'], reason='unit_test_restart')
    assert restarted is not None
    assert restarted['status'] == 'running'
    assert restarted['health']['last_restart_reason'] == 'unit_test_restart'
    assert restarted['restart_history'][-1]['reason'] == 'unit_test_restart'
    deleted = await service.delete_agent_instance(created['instance_id'])
    assert deleted is not None
    assert deleted['deleted'] is True

    registered = await service.register_external_workflow(
        'custom_review_flow',
        {
            'active_framework': 'dify-compatible',
            'fallback_framework': 'native-python',
            'runtime_mode': 'template-routing',
            'diagnostics': {'template_routing_supported': True},
        },
    )
    assert registered['workflow_key'] == 'custom_review_flow'
    workflows = await service.list_registered_workflows()
    assert workflows['total'] >= 4
    assert any(item['workflow_key'] == 'custom_review_flow' for item in workflows['items'])

    workflow = await service.invoke_workflow(
        framework_key='langgraph-compatible',
        input_data={'query': '蓝牙耳机', 'category': 'electronics', 'target_market': 'US'},
        breakpoints=['risk_assessment'],
        single_step=True,
    )
    assert workflow['snapshot']['framework'] == 'langgraph-compatible'
    assert workflow['single_step'] is True

    snapshot_id = workflow['snapshot']['snapshot_id']
    snapshot = await service.get_workflow_snapshot(snapshot_id)
    assert snapshot is not None
    assert snapshot['snapshot_id'] == snapshot_id

    stepped = await service.step_workflow_snapshot(snapshot_id)
    assert stepped['single_step'] is True

    resumed = await service.resume_workflow_snapshot(snapshot_id, human_input={'action': 'approve', 'comment': '继续执行'})
    assert resumed['status'] in {'waiting_human_input', 'completed', 'running'}

    autogen_workflow = await service.invoke_workflow(
        framework_key='autogen-compatible',
        input_data={'query': '蓝牙耳机', 'category': 'electronics', 'target_market': 'US'},
    )
    assert autogen_workflow['framework'] == 'autogen-compatible'
    assert autogen_workflow['conversation_mode'] == 'multi_agent_dialogue'
    assert len(autogen_workflow['participants']) >= 4
    assert 'source_summary' in autogen_workflow
    assert autogen_workflow['collection_readiness']['governance_status'] == 'local_validation_only'
    assert autogen_workflow['business_summary']['operations_view']
    assert autogen_workflow['framework_runtime']['compatible_runtime'] is True

    langchain_workflow = await service.invoke_workflow(
        framework_key='langchain-compatible',
        input_data={'query': '蓝牙耳机', 'category': 'electronics', 'target_market': 'US'},
    )
    assert langchain_workflow['framework'] == 'langchain-compatible'
    assert langchain_workflow['execution_mode'] == 'tool_calling_chain'
    assert len(langchain_workflow['tool_calls']) == 3
    assert langchain_workflow['collection_readiness']['governance_status'] == 'local_validation_only'
    assert langchain_workflow['business_summary']['pricing_enterprise_ready'] is False
    assert langchain_workflow['business_summary']['finance_view']
    assert 'diagnostics' in langchain_workflow['framework_runtime']

    crewai_workflow = await service.invoke_workflow(
        framework_key='crewai-compatible',
        input_data={'query': '蓝牙耳机', 'category': 'electronics', 'target_market': 'US'},
    )
    assert crewai_workflow['framework'] == 'crewai-compatible'
    assert crewai_workflow['execution_mode'] == 'parallel_task_crew'
    assert len(crewai_workflow['crew']['tasks']) == 3
    assert crewai_workflow['business_summary']['competitor_scan_enterprise_ready'] is False
    assert crewai_workflow['business_summary']['next_action']

    ray_workflow = await service.invoke_workflow(
        framework_key='ray-compatible',
        input_data={'query': '蓝牙耳机', 'category': 'electronics', 'target_market': 'US'},
    )
    assert ray_workflow['framework'] == 'ray-compatible'
    assert ray_workflow['execution_mode'] == 'actor_parallelism'
    assert len(ray_workflow['actors']) == 3
    assert ray_workflow['business_summary']['market_signal_enterprise_ready'] is False

    dify_workflow = await service.invoke_workflow(
        framework_key='dify-compatible',
        input_data={'query': '输出蓝牙耳机市场机会摘要', 'category': 'electronics'},
    )
    assert dify_workflow['framework'] == 'dify-compatible'
    assert dify_workflow['execution_mode'] == 'prompt_orchestration'
    assert dify_workflow['routing']['template_key'] == 'selection-electronics-brief'
    assert dify_workflow['business_summary']['next_action']

    published = await service.publish_agent_message(
        sender='planner',
        receiver='collector',
        content={'task_id': 'task-3', 'stage': 'collect'},
        message_type='status_update',
        correlation_id='corr-task-3',
        metadata={'task_id': 'task-3'},
    )
    assert published['published'] is True
    assert published['message_bus']['kafka_compatibility']['local_acceptance_ready'] is True
    assert published['message_bus']['kafka_compatibility']['real_broker_status'] == 'blocked'

    operations = await service.build_operations_status()
    assert operations['running_total'] == 1
    assert operations['dead_letter_total'] == 1
    assert operations['retryable_total'] == 1
    assert operations['manual_intervention_total'] >= 1
    assert operations['failed_reasons']['执行失败'] == 1
    assert any(item['retry_count'] == 3 for item in operations['retry_history'])
    assert any(item['action'] == 'resume' for item in operations['recent_interventions'])
    assert operations['lifecycle_summary']['running'] == 1
    assert operations['lifecycle_summary']['dead_letter'] == 1
    assert operations['agent_instance_lifecycle']['auto_restart_ready'] is True
    assert operations['agent_instance_lifecycle']['auto_restart_supported'] is True
    assert operations['agent_instance_lifecycle']['restart_policy_default'] == 'on_failure'
    assert 'manual_intervene' in operations['lifecycle_actions']
    assert 'langgraph-compatible' in operations['framework_usage']
    assert operations['diagnostics']['status'] == 'ready'
    assert operations['diagnostics']['message_bus_trace_ready'] is True
    assert operations['message_bus']['trace_summary']['trace_ready'] is True
    assert operations['message_bus']['trace_summary']['task_associations']
    assert operations['kafka_compatibility']['mode'] == 'kafka-compatible-local-persistence'
    assert operations['kafka_compatibility']['local_acceptance_ready'] is True
    assert operations['kafka_compatibility']['real_broker_status'] == 'blocked'
    assert operations['message_bus']['ordered_offset_ready'] is True

    rollback = await service.rollback_workflow_snapshot(snapshot_id, target_node='market_analysis')
    assert rollback['rolled_back'] is True
    assert rollback['rollback_ready'] is True
    assert rollback['rollback_scope'] == 'workflow-snapshot'


@pytest.mark.asyncio
async def test_agent_platform_service_uses_real_dify_runtime_when_available():
    service = AgentPlatformService(session=None, tenant_id='tenant-dify', actor={'username': 'tester'})

    class _ReadyDifyService:
        def build_runtime_status(self):
            return {
                'enabled': True,
                'base_url': 'http://dify.local',
                'workflow_run_path': '/v1/workflows/run',
                'workflow_endpoint': 'http://dify.local/v1/workflows/run',
                'api_key_configured': True,
                'configuration_ready': True,
                'real_runtime_ready': True,
                'timeout_seconds': 20.0,
                'response_mode': 'blocking',
                'user_prefix': 'pms',
                'prefer_compatible_fallback': True,
                'runtime_status': 'active',
                'blocked_reason': None,
                'last_error': None,
            }

        async def invoke_workflow(self, *, input_data):
            return {
                'framework': 'dify-compatible',
                'status': 'succeeded',
                'execution_mode': 'prompt_orchestration',
                'runtime_channel': 'dify-http',
                'routing': {
                    'template_key': 'selection-electronics-brief',
                    'channel': 'dify-http',
                    'strategy': 'workflow-api',
                },
                'business_summary': {'next_action': '继续人工复核'},
                'dify_runtime': self.build_runtime_status(),
                'variables': input_data,
            }

    service.dify_workflow_service = _ReadyDifyService()
    result = await service.invoke_workflow(
        framework_key='dify-compatible',
        input_data={'query': '输出蓝牙耳机市场机会摘要', 'category': 'electronics', 'target_market': 'US'},
    )

    assert result['runtime_channel'] == 'dify-http'
    assert result['dify_runtime']['runtime_status'] == 'active'
    assert result['framework_runtime']['dify_runtime']['workflow_endpoint'] == 'http://dify.local/v1/workflows/run'


@pytest.mark.asyncio
async def test_agent_platform_service_falls_back_when_dify_runtime_errors():
    service = AgentPlatformService(session=None, tenant_id='tenant-dify-fallback', actor={'username': 'tester'})

    class _FailingDifyService:
        error_message = 'Dify workflow invocation failed: timed out'

        def build_runtime_status(self):
            return {
                'enabled': True,
                'base_url': 'http://dify.local',
                'workflow_run_path': '/v1/workflows/run',
                'workflow_endpoint': 'http://dify.local/v1/workflows/run',
                'api_key_configured': True,
                'configuration_ready': True,
                'real_runtime_ready': True,
                'timeout_seconds': 20.0,
                'response_mode': 'blocking',
                'user_prefix': 'pms',
                'prefer_compatible_fallback': True,
                'runtime_status': 'fallback',
                'blocked_reason': self.error_message,
                'last_error': self.error_message,
            }

        async def invoke_workflow(self, *, input_data):
            raise DifyWorkflowError(self.error_message)

    service.dify_workflow_service = _FailingDifyService()
    result = await service.invoke_workflow(
        framework_key='dify-compatible',
        input_data={'query': '输出蓝牙耳机市场机会摘要', 'category': 'electronics'},
    )

    assert result['runtime_channel'] == 'dify-compatible'
    assert result['fallback'] is True
    assert result['provider_error'] == 'Dify workflow invocation failed: timed out'
    assert result['routing']['fallback_from'] == 'dify-http'
    assert result['framework_runtime']['dify_runtime']['runtime_status'] == 'fallback'
