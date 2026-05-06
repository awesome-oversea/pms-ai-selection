"""
SQLAlchemy ORM 基类
===================

D03-04 任务: 统一 ORM Base 定义

所有业务模型继承此 Base，确保:
- 建表使用同一份 metadata
- Base 定义不重复声明

使用方式:
    from src.models.base import Base

    class Product(Base):
        __tablename__ = "products"
        ...
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    SQLAlchemy 声明式基类。

    所有 ORM 模型继承此类。
    """
    pass
