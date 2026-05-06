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
    
    # 检查 OMS 系统配置
    oms_config = await repo.get_config(ERPSystemType.OMS)
    print('OMS配置:', oms_config)
    
    # 检查 SCM 系统配置
    scm_config = await repo.get_config(ERPSystemType.SCM)
    print('SCM配置:', scm_config)
    
    # 检查 WMS 系统配置
    wms_config = await repo.get_config(ERPSystemType.WMS)
    print('WMS配置:', wms_config)
    
    # 检查 CRM 系统配置
    crm_config = await repo.get_config(ERPSystemType.CRM)
    print('CRM配置:', crm_config)
    
    # 检查 FMS 系统配置
    fms_config = await repo.get_config(ERPSystemType.FMS)
    print('FMS配置:', fms_config)
    
    # 检查 BI 系统配置
    bi_config = await repo.get_config(ERPSystemType.BI)
    print('BI配置:', bi_config)
    
    # 检查 PaaS 系统配置
    paas_config = await repo.get_config(ERPSystemType.PAAS)
    print('PaaS配置:', paas_config)
    
    await session.close()

if __name__ == '__main__':
    asyncio.run(main())