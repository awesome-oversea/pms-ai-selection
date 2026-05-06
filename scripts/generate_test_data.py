#!/usr/bin/env python3
"""
测试数据生成脚本
用于生成选品系统所需的测试数据，确保本地环境有足够的数据进行验证
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config.settings import get_settings
from src.infrastructure.database import init_db, close_db
from src.models.schemas import SelectionTaskRunCreate
from src.services.selection_service import SelectionTaskService

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class TestDataGenerator:
    """测试数据生成器"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.service = SelectionTaskService(session)
        self.categories = [
            "electronics", "fashion", "home", "beauty", "sports",
            "toys", "books", "food", "health", "automotive"
        ]
        self.target_markets = ["US", "EU", "JP", "AU", "CA"]
        self.queries = [
            "wireless earbuds", "smartwatch", "Bluetooth speaker", "portable charger",
            "fitness tracker", "gaming mouse", "keyboard", "monitor", "laptop",
            "smartphone", "headphones", "camera", "action camera", "drone"
        ]

    async def generate_users(self, count: int = 5) -> list[dict[str, Any]]:
        """生成用户数据"""
        users = []
        for i in range(count):
            user = {
                "id": f"user_{i+1}",
                "name": f"User {i+1}",
                "email": f"user{i+1}@example.com",
                "tenant_id": f"tenant_{(i % 2) + 1}"
            }
            users.append(user)
        logger.info(f"生成了 {len(users)} 个用户")
        return users

    async def generate_selection_tasks(self, count: int = 20) -> list[dict[str, Any]]:
        """生成选品任务数据"""
        tasks = []
        users = await self.generate_users()
        
        for i in range(count):
            user = random.choice(users)
            task_data = SelectionTaskRunCreate(
                query=random.choice(self.queries),
                category=random.choice(self.categories),
                target_market=random.choice(self.target_markets),
                investment_budget=random.uniform(10000, 100000),
                auto_approve=random.choice([True, False]),
                priority=random.choice(["low", "normal", "high"])
            )
            
            try:
                task = await self.service.create_task(
                    task_data.model_dump(),
                    created_by=user["id"],
                    tenant_id=user["tenant_id"]
                )
                tasks.append(task)
                logger.info(f"生成选品任务: {task['task_id']} - {task['query']}")
            except Exception as e:
                logger.error(f"生成选品任务失败: {e}")
        
        logger.info(f"生成了 {len(tasks)} 个选品任务")
        return tasks

    async def generate_task_results(self, tasks: list[dict[str, Any]]):
        """为任务生成结果数据"""
        for task in tasks:
            try:
                # 模拟任务执行结果
                result_payload = {
                    "data_collection": {
                        "amazon_data": {
                            "products": [
                                {
                                    "id": "B08X5G8Q2Y",
                                    "title": f"{task['query']} Pro",
                                    "price": random.uniform(20, 200),
                                    "rating": random.uniform(3.5, 5.0),
                                    "review_count": random.randint(100, 10000)
                                }
                            ]
                        },
                        "tiktok_data": {
                            "trends": [
                                {
                                    "hashtag": f"#{task['query'].replace(' ', '')}",
                                    "views": random.randint(100000, 10000000)
                                }
                            ]
                        },
                        "trend_data": {
                            "interest_over_time": [
                                {"date": "2026-04-01", "value": random.randint(60, 90)},
                                {"date": "2026-04-02", "value": random.randint(60, 90)},
                                {"date": "2026-04-03", "value": random.randint(60, 90)}
                            ]
                        },
                        "supplier_data": {
                            "suppliers": [
                                {
                                    "id": "12345",
                                    "name": "Shenzhen Electronics Co.",
                                    "min_order": random.randint(5, 50),
                                    "price": random.uniform(10, 100)
                                }
                            ]
                        }
                    },
                    "market_analysis": {
                        "opportunity_score": {
                            "overall": random.uniform(50, 95),
                            "factors": [
                                {"name": "demand", "score": random.uniform(60, 95)},
                                {"name": "competition", "score": random.uniform(40, 80)},
                                {"name": "trend", "score": random.uniform(60, 95)}
                            ]
                        },
                        "trends": {
                            "direction": random.choice(["up", "stable", "down"]),
                            "strength": random.uniform(0.1, 1.0),
                            "confidence": random.uniform(0.7, 0.99)
                        }
                    },
                    "product_planning": {
                        "top_recommendation": {
                            "product_name": f"{task['query']} Elite",
                            "confidence": random.uniform(0.7, 0.99),
                            "expected_roi": random.uniform(1.5, 3.0)
                        },
                        "product_spec": {
                            "name": f"{task['query']} Elite",
                            "positioning": "premium",
                            "core_features": ["wireless", "bluetooth 5.0", "noise cancellation"],
                            "selling_points": ["high quality", "affordable price", "long battery life"],
                            "target_price": [random.uniform(50, 150), random.uniform(100, 200)]
                        },
                        "differentiation": {
                            "overall": random.uniform(50, 90),
                            "factors": [
                                {"name": "features", "score": random.uniform(60, 95)},
                                {"name": "price", "score": random.uniform(60, 95)},
                                {"name": "branding", "score": random.uniform(40, 80)}
                            ]
                        }
                    },
                    "commercial_evaluation": {
                        "go_no_go": {
                            "decision": random.choice(["GO", "NO_GO", "CONDITIONAL_GO"]),
                            "confidence": random.uniform(0.7, 0.99),
                            "recommendation": "Based on market analysis and financial projection"
                        },
                        "financial_projection": {
                            "roi_pct": random.uniform(50, 200),
                            "gross_margin": random.uniform(0.3, 0.6),
                            "net_margin": random.uniform(0.1, 0.3),
                            "ltv_cac_ratio": random.uniform(3, 8)
                        },
                        "pricing_suggestion": {
                            "recommended_price": random.uniform(80, 180),
                            "pricing_strategy": random.choice(["penetration", "premium", "competitive"])
                        },
                        "risk_assessment": {
                            "top_risks": [
                                {"name": "competition", "category": "market", "score": random.uniform(30, 70)},
                                {"name": "supply chain", "category": "operation", "score": random.uniform(20, 60)},
                                {"name": "regulatory", "category": "legal", "score": random.uniform(10, 50)}
                            ]
                        }
                    }
                }
                
                # 更新任务结果
                from src.repositories.selection_repository import SelectionTaskRepository
                from src.models.enums import TaskStatus
                
                repo = SelectionTaskRepository(self.session, tenant_id=task.get("tenant_id"))
                import uuid
                task_uuid = uuid.UUID(task["task_id"])
                await repo.update_task_status(
                    task_uuid,
                    TaskStatus.COMPLETED,
                    result_summary=f"选品分析完成: {task['query']}"
                )
                
                # 更新任务配置
                db_task = await repo.get_task(task_uuid)
                if db_task:
                    config = db_task.config or {}
                    config["execution_result"] = result_payload
                    config["go_no_go"] = result_payload["commercial_evaluation"]["go_no_go"]
                    config["go_no_go_decision"] = result_payload["commercial_evaluation"]["go_no_go"]["decision"]
                    db_task.config = config
                    await self.session.commit()
                    logger.info(f"更新任务结果: {task['task_id']}")
                    
            except Exception as e:
                logger.error(f"生成任务结果失败: {e}")

    async def generate_feedback(self, tasks: list[dict[str, Any]], count: int = 3):
        """为任务生成反馈数据"""
        for task in tasks:
            for i in range(count):
                try:
                    feedback = {
                        "rating": random.uniform(1, 5),
                        "sentiment": random.choice(["positive", "neutral", "negative"]),
                        "tags": random.sample(["quality", "price", "delivery", "service", "features"], 2),
                        "comment": f"Test feedback {i+1} for {task['query']}",
                        "source": random.choice(["customer", "internal", "market"])
                    }
                    await self.service.add_feedback(task["task_id"], feedback)
                    logger.info(f"为任务 {task['task_id']} 生成反馈 {i+1}")
                except Exception as e:
                    logger.error(f"生成反馈失败: {e}")

    async def generate_all(self, task_count: int = 20, feedback_count: int = 3):
        """生成所有测试数据"""
        logger.info("开始生成测试数据...")
        
        # 生成选品任务
        tasks = await self.generate_selection_tasks(task_count)
        
        # 生成任务结果
        await self.generate_task_results(tasks)
        
        # 生成反馈
        await self.generate_feedback(tasks, feedback_count)
        
        logger.info("测试数据生成完成!")
        return tasks


async def main() -> int:
    """主函数"""
    parser = argparse.ArgumentParser(description="生成测试数据")
    parser.add_argument("--task-count", type=int, default=20, help="生成的任务数量")
    parser.add_argument("--feedback-count", type=int, default=3, help="每个任务的反馈数量")
    parser.add_argument("--reset", action="store_true", help="重置数据库")
    
    args = parser.parse_args()
    
    try:
        # 初始化数据库
        logger.info("初始化数据库...")
        await init_db()
        
        # 创建会话
        settings = get_settings()
        engine = create_async_engine(settings.database.url)
        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session() as session:
            generator = TestDataGenerator(session)
            await generator.generate_all(args.task_count, args.feedback_count)
        
        # 关闭数据库
        await close_db()
        
        logger.info("测试数据生成成功!")
        return 0
        
    except Exception as e:
        logger.error(f"生成测试数据失败: {e}")
        return 1


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())