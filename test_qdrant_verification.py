"""
Qdrant 真验收测试
==================
验证 Qdrant 服务的实际连接和基本功能。
"""

import asyncio
import sys
import requests


def test_qdrant_http_api():
    """通过 HTTP API 测试 Qdrant 连接。"""
    base_url = "http://localhost:6333"
    
    # 1. 测试服务是否可达
    try:
        resp = requests.get(f"{base_url}/")
        if resp.status_code == 200:
            info = resp.json()
            print(f"✅ Qdrant 服务可达")
            print(f"   版本: {info.get('version', 'unknown')}")
            print(f"   标题: {info.get('title', 'unknown')}")
        else:
            print(f"❌ Qdrant 服务返回异常状态码: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Qdrant 服务不可达: {e}")
        return False

    # 2. 测试获取集合列表
    try:
        resp = requests.get(f"{base_url}/collections")
        if resp.status_code == 200:
            data = resp.json()
            collections = data.get('result', {}).get('collections', [])
            print(f"✅ 集合列表获取成功: {len(collections)} 个集合")
            for coll in collections:
                print(f"   - {coll.get('name', 'unknown')}")
        else:
            print(f"⚠️  集合列表获取失败: HTTP {resp.status_code}")
    except Exception as e:
        print(f"⚠️  集合列表获取异常: {e}")

    # 3. 创建测试集合
    test_collection = "test_verification"
    try:
        # 先删除可能存在的测试集合
        requests.delete(f"{base_url}/collections/{test_collection}")
        
        # 创建新集合
        create_payload = {
            "vectors": {
                "size": 4,
                "distance": "Cosine"
            }
        }
        resp = requests.put(
            f"{base_url}/collections/{test_collection}",
            json=create_payload
        )
        if resp.status_code == 200:
            print(f"✅ 测试集合创建成功: {test_collection}")
        else:
            print(f"❌ 测试集合创建失败: HTTP {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"❌ 测试集合创建异常: {e}")
        return False

    # 4. 插入向量
    try:
        upsert_payload = {
            "points": [
                {
                    "id": 1,
                    "vector": [0.1, 0.2, 0.3, 0.4],
                    "payload": {"test": "data", "type": "verification"}
                },
                {
                    "id": 2,
                    "vector": [0.5, 0.6, 0.7, 0.8],
                    "payload": {"test": "data", "type": "verification"}
                }
            ]
        }
        resp = requests.put(
            f"{base_url}/collections/{test_collection}/points",
            json=upsert_payload
        )
        if resp.status_code == 200:
            print(f"✅ 向量插入成功")
        else:
            print(f"❌ 向量插入失败: HTTP {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"❌ 向量插入异常: {e}")
        return False

    # 5. 搜索向量
    try:
        search_payload = {
            "vector": [0.15, 0.25, 0.35, 0.45],
            "limit": 2
        }
        resp = requests.post(
            f"{base_url}/collections/{test_collection}/points/search",
            json=search_payload
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get('result', [])
            print(f"✅ 向量搜索成功: 找到 {len(results)} 个结果")
            for result in results:
                print(f"   - ID: {result.get('id')}, Score: {result.get('score')}")
        else:
            print(f"❌ 向量搜索失败: HTTP {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"❌ 向量搜索异常: {e}")
        return False

    # 6. 清理测试集合
    try:
        resp = requests.delete(f"{base_url}/collections/{test_collection}")
        if resp.status_code == 200:
            print(f"✅ 测试集合清理成功: {test_collection}")
        else:
            print(f"⚠️  测试集合清理失败: HTTP {resp.status_code}")
    except Exception as e:
        print(f"⚠️  测试集合清理异常: {e}")

    return True


async def main():
    """主函数。"""
    print("=" * 50)
    print("Qdrant 真验收测试 (HTTP API)")
    print("=" * 50)

    success = test_qdrant_http_api()

    print("\n" + "=" * 50)
    if success:
        print("✅ 验收结果: 通过")
        print("\nQdrant 服务状态:")
        print("  - 服务运行: ✅")
        print("  - HTTP API: ✅")
        print("  - 集合管理: ✅")
        print("  - 向量插入: ✅")
        print("  - 向量搜索: ✅")
        sys.exit(0)
    else:
        print("❌ 验收结果: 失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
