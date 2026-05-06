"""
Repository数据访问层。

提供对数据库模型的CRUD操作封装，
将SQL操作与业务逻辑解耦。
"""

from src.repositories.knowledge_repository import KnowledgeRepository
from src.repositories.selection_repository import SelectionTaskRepository

__all__ = ["SelectionTaskRepository", "KnowledgeRepository"]
