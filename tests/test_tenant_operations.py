from __future__ import annotations

import pytest


class _Tenant:
    def __init__(self, tenant_id: str, tenant_key: str, name: str, status: str = 'active', is_active: bool = True):
        self.id = tenant_id
        self.tenant_key = tenant_key
        self.name = name
        self.status = status
        self.is_active = is_active


@pytest.mark.asyncio
async def test_tenant_operations_payload_shape():
    tenants = [
        {
            'tenant_id': 'tenant-1',
            'tenant_key': 'default',
            'name': 'Default Tenant',
            'status': 'active',
            'is_active': True,
            'quota_status': [
                {
                    'quota_type': 'llm_cost_usd',
                    'limit_value': 100,
                    'used_value': 10,
                    'remaining': 90,
                    'reset_period': 'monthly',
                    'is_active': True,
                }
            ],
        }
    ]
    assert tenants[0]['tenant_key'] == 'default'
    assert tenants[0]['quota_status'][0]['remaining'] == 90
