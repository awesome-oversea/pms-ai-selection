import sys
import os

# 添加父目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.search_backend import get_search_backend

async def test_search_backend():
    search_backend = get_search_backend()
    status = search_backend.build_status()
    print("Search Backend Status:")
    print(f"Enabled: {status['enabled']}")
    print(f"Backend: {status['backend']}")
    print(f"Endpoint: {status['endpoint']}")
    print(f"Client Configured: {status['client_configured']}")
    print(f"Effective Mode: {status['effective_mode']}")
    print(f"Memory Doc Count: {status['memory_doc_count']}")
    
    # 测试索引文档
    index_name = "test_index"
    test_docs = [
        {
            "id": "1",
            "content": "EcoFlow是一家专注于户外储能电源的品牌，其产品包括RIVER系列和DELTA系列。",
            "metadata": {
                "tenant_id": "test-tenant",
                "document_id": "doc1",
                "chunk_index": 0,
                "source": "test"
            }
        },
        {
            "id": "2",
            "content": "Jackery是EcoFlow的主要竞争对手，也提供类似的户外储能解决方案。",
            "metadata": {
                "tenant_id": "test-tenant",
                "document_id": "doc2",
                "chunk_index": 0,
                "source": "test"
            }
        }
    ]
    
    print("\nIndexing test documents...")
    await search_backend.index_documents(index_name, test_docs)
    
    # 测试搜索
    print("\nTesting keyword search...")
    results = await search_backend.keyword_search(index_name, "EcoFlow", 10, {"tenant_id": "test-tenant"})
    print(f"Search results count: {len(results)}")
    for i, result in enumerate(results):
        print(f"Result {i+1}: Score={result['score']}, Content={result['content'][:100]}...")
    
    # 再次检查状态
    status = search_backend.build_status()
    print("\nUpdated Search Backend Status:")
    print(f"Memory Doc Count: {status['memory_doc_count']}")
    print(f"Last Reindex: {status['last_reindex']}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_search_backend())
