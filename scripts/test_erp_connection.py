import sys
import os

# 添加父目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.database import get_async_session_factory
from src.repositories.erp_repository import ErpIntegrationRepository
from src.models.enums import ERPSystemType
import asyncio

async def main():
    session = get_async_session_factory()()
    repo = ErpIntegrationRepository(session)
    
    try:
        # 检查 OMS 系统配置
        oms_config = await repo.get_config(ERPSystemType.OMS)
        print('OMS配置:', oms_config)
        print('OMS配置ID:', oms_config.id if oms_config else None)
        print('OMS配置名称:', oms_config.name if oms_config else None)
        print('OMS配置API端点:', oms_config.api_endpoint if oms_config else None)
        print('OMS配置是否活跃:', oms_config.is_active if oms_config else None)
        print('OMS配置额外配置:', oms_config.extra_config if oms_config else None)
        
        # 检查 SCM 系统配置
        scm_config = await repo.get_config(ERPSystemType.SCM)
        print('\nSCM配置:', scm_config)
        print('SCM配置ID:', scm_config.id if scm_config else None)
        print('SCM配置名称:', scm_config.name if scm_config else None)
        print('SCM配置API端点:', scm_config.api_endpoint if scm_config else None)
        print('SCM配置是否活跃:', scm_config.is_active if scm_config else None)
        print('SCM配置额外配置:', scm_config.extra_config if scm_config else None)
        
        # 检查 CRM 系统配置
        crm_config = await repo.get_config(ERPSystemType.CRM)
        print('\nCRM配置:', crm_config)
        print('CRM配置ID:', crm_config.id if crm_config else None)
        print('CRM配置名称:', crm_config.name if crm_config else None)
        print('CRM配置API端点:', crm_config.api_endpoint if crm_config else None)
        print('CRM配置是否活跃:', crm_config.is_active if crm_config else None)
        print('CRM配置额外配置:', crm_config.extra_config if crm_config else None)
        
        # 检查 PaaS 系统配置
        paas_config = await repo.get_config(ERPSystemType.PAAS)
        print('\nPaaS配置:', paas_config)
        print('PaaS配置ID:', paas_config.id if paas_config else None)
        print('PaaS配置名称:', paas_config.name if paas_config else None)
        print('PaaS配置API端点:', paas_config.api_endpoint if paas_config else None)
        print('PaaS配置是否活跃:', paas_config.is_active if paas_config else None)
        print('PaaS配置额外配置:', paas_config.extra_config if paas_config else None)
        
    finally:
        await session.close()

if __name__ == '__main__':
    asyncio.run(main())