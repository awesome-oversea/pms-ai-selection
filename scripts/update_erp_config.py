import sys
import os
import asyncio

# 添加父目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.database import get_async_session
from src.repositories.erp_repository import ErpIntegrationRepository
from src.models.enums import ERPSystemType

async def update_config():
    async with get_async_session() as session:
        repo = ErpIntegrationRepository(session)
        
        # 更新OMS配置
        oms_config = await repo.get_config(ERPSystemType.OMS, name='default')
        if oms_config:
            oms_config.api_endpoint = 'http://localhost:8000'
            await session.commit()
            print('已更新OMS配置')
        
        # 更新SCM配置
        scm_config = await repo.get_config(ERPSystemType.SCM, name='default')
        if scm_config:
            scm_config.api_endpoint = 'http://localhost:8000'
            await session.commit()
            print('已更新SCM配置')
        
        # 更新CRM配置
        crm_config = await repo.get_config(ERPSystemType.CRM, name='default')
        if crm_config:
            crm_config.api_endpoint = 'http://localhost:8000'
            await session.commit()
            print('已更新CRM配置')
        
        # 更新PaaS配置
        paas_config = await repo.get_config(ERPSystemType.PAAS, name='default')
        if paas_config:
            paas_config.api_endpoint = 'http://localhost:8000'
            await session.commit()
            print('已更新PaaS配置')
        
        print('ERP配置更新完成！')

if __name__ == '__main__':
    asyncio.run(update_config())
