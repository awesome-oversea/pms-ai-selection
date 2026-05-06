import sys
import os
import asyncio

# 添加父目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.database import get_async_session
from src.repositories.erp_repository import ErpIntegrationRepository
from src.models.enums import ERPSystemType

async def check_config():
    async with get_async_session() as session:
        repo = ErpIntegrationRepository(session)
        
        configs = []
        for system in [ERPSystemType.OMS, ERPSystemType.SCM, ERPSystemType.CRM, ERPSystemType.PAAS]:
            config = await repo.get_config(system, name='default')
            if config:
                configs.append({
                    'system': system.value,
                    'api_endpoint': config.api_endpoint,
                    'extra_config': config.extra_config
                })
        
        print('当前ERP配置:')
        for config in configs:
            print(f"系统: {config['system']}")
            print(f"API端点: {config['api_endpoint']}")
            print(f"额外配置: {config['extra_config']}")
            print()

if __name__ == '__main__':
    asyncio.run(check_config())
