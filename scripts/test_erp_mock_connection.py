import sys
import os
import httpx

# 添加父目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_oms_connection():
    """测试 OMS 模拟服务连接"""
    url = "http://localhost:8000/api/v1/integration/oms/test-connection"
    headers = {
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlcnBfdGVzdF91c2VyIiwidXNlcl9pZCI6IjVhZDFiZjNmLWFlZWQtNDU3OC05ZmU2LTk5NTY2ZjA3Mjk2ZCIsImlzX3N1cGVydXNlciI6ZmFsc2UsInRlbmFudF9pZCI6Ijg2ZDFmNzk2LTdjNTUtNTdhMS1hYzc3LTJlOTUyYTIxMTFjYSIsInRlbmFudF9rZXkiOiJkZWZhdWx0IiwidGVuYW50X25hbWUiOiJcdTllZDhcdThiYTRcdTc5ZGZcdTYyMzciLCJleHAiOjE3NzYwOTgzMzYsInR5cGUiOiJhY2Nlc3MifQ.8vYZf1QaQEjK7FMsmuXJxyrwQsLzUjmj8bxcwIdYxEI",
        "Content-Type": "application/json"
    }
    payload = {
        "name": "default"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            print(f"OMS 连接测试响应状态码: {response.status_code}")
            print(f"OMS 连接测试响应内容: {response.json()}")
    except Exception as e:
        print(f"OMS 连接测试失败: {e}")

async def test_scm_connection():
    """测试 SCM 模拟服务连接"""
    url = "http://localhost:8000/api/v1/integration/scm/test-connection"
    headers = {
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlcnBfdGVzdF91c2VyIiwidXNlcl9pZCI6IjVhZDFiZjNmLWFlZWQtNDU3OC05ZmU2LTk5NTY2ZjA3Mjk2ZCIsImlzX3N1cGVydXNlciI6ZmFsc2UsInRlbmFudF9pZCI6Ijg2ZDFmNzk2LTdjNTUtNTdhMS1hYzc3LTJlOTUyYTIxMTFjYSIsInRlbmFudF9rZXkiOiJkZWZhdWx0IiwidGVuYW50X25hbWUiOiJcdTllZDhcdThiYTRcdTc5ZGZcdTYyMzciLCJleHAiOjE3NzYwOTgzMzYsInR5cGUiOiJhY2Nlc3MifQ.8vYZf1QaQEjK7FMsmuXJxyrwQsLzUjmj8bxcwIdYxEI",
        "Content-Type": "application/json"
    }
    payload = {
        "name": "default"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            print(f"SCM 连接测试响应状态码: {response.status_code}")
            print(f"SCM 连接测试响应内容: {response.json()}")
    except Exception as e:
        print(f"SCM 连接测试失败: {e}")

async def test_crm_connection():
    """测试 CRM 模拟服务连接"""
    url = "http://localhost:8000/api/v1/integration/crm/test-connection"
    headers = {
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlcnBfdGVzdF91c2VyIiwidXNlcl9pZCI6IjVhZDFiZjNmLWFlZWQtNDU3OC05ZmU2LTk5NTY2ZjA3Mjk2ZCIsImlzX3N1cGVydXNlciI6ZmFsc2UsInRlbmFudF9pZCI6Ijg2ZDFmNzk2LTdjNTUtNTdhMS1hYzc3LTJlOTUyYTIxMTFjYSIsInRlbmFudF9rZXkiOiJkZWZhdWx0IiwidGVuYW50X25hbWUiOiJcdTllZDhcdThiYTRcdTc5ZGZcdTYyMzciLCJleHAiOjE3NzYwOTgzMzYsInR5cGUiOiJhY2Nlc3MifQ.8vYZf1QaQEjK7FMsmuXJxyrwQsLzUjmj8bxcwIdYxEI",
        "Content-Type": "application/json"
    }
    payload = {
        "name": "default"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            print(f"CRM 连接测试响应状态码: {response.status_code}")
            print(f"CRM 连接测试响应内容: {response.json()}")
    except Exception as e:
        print(f"CRM 连接测试失败: {e}")

async def test_paas_connection():
    """测试 PaaS 模拟服务连接"""
    url = "http://localhost:8000/api/v1/integration/paas/test-connection"
    headers = {
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlcnBfdGVzdF91c2VyIiwidXNlcl9pZCI6IjVhZDFiZjNmLWFlZWQtNDU3OC05ZmU2LTk5NTY2ZjA3Mjk2ZCIsImlzX3N1cGVydXNlciI6ZmFsc2UsInRlbmFudF9pZCI6Ijg2ZDFmNzk2LTdjNTUtNTdhMS1hYzc3LTJlOTUyYTIxMTFjYSIsInRlbmFudF9rZXkiOiJkZWZhdWx0IiwidGVuYW50X25hbWUiOiJcdTllZDhcdThiYTRcdTc5ZGZcdTYyMzciLCJleHAiOjE3NzYwOTgzMzYsInR5cGUiOiJhY2Nlc3MifQ.8vYZf1QaQEjK7FMsmuXJxyrwQsLzUjmj8bxcwIdYxEI",
        "Content-Type": "application/json"
    }
    payload = {
        "name": "default"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            print(f"PaaS 连接测试响应状态码: {response.status_code}")
            print(f"PaaS 连接测试响应内容: {response.json()}")
    except Exception as e:
        print(f"PaaS 连接测试失败: {e}")

async def main():
    print("测试 ERP 模拟服务连接...")
    await test_oms_connection()
    print("\n")
    await test_scm_connection()
    print("\n")
    await test_crm_connection()
    print("\n")
    await test_paas_connection()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())