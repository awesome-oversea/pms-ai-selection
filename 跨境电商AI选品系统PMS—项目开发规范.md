# 跨境电商AI选品系统PMS—项目开发规范

> **版本**：v1.0
> **创建日期**：2026-04-23
> **项目代号**：Project Aegis
> **文档状态**：正式版
> **适用对象**：全体开发人员

------

## 目录

1. **规范概述**
   - 1.1 规范目的
   - 1.2 规范原则
   - 1.3 规范等级
   - 1.4 规范更新机制
2. **代码规范**
   - 2.1 Python代码规范
   - 2.2 TypeScript/JavaScript代码规范
   - 2.3 SQL代码规范
   - 2.4 配置文件规范
3. **项目结构规范**
   - 3.1 后端项目结构
   - 3.2 前端项目结构
   - 3.3 微服务命名规范
   - 3.4 包命名规范
4. **API设计规范**
   - 4.1 RESTful API规范
   - 4.2 WebSocket规范
   - 4.3 gRPC规范
   - 4.4 错误码规范
5. **数据库规范**
   - 5.1 表命名规范
   - 5.2 字段命名规范
   - 5.3 索引命名规范
   - 5.4 SQL编写规范
6. **Git工作流规范**
   - 6.1 分支策略
   - 6.2 Commit规范
   - 6.3 PR/MR规范
   - 6.4 代码审查规范
7. **测试规范**
   - 7.1 单元测试规范
   - 7.2 集成测试规范
   - 7.3 端到端测试规范
   - 7.4 性能测试规范
8. **文档规范**
   - 8.1 代码注释规范
   - 8.2 API文档规范
   - 8.3 架构文档规范
   - 8.4 README规范
9. **安全规范**
   - 9.1 认证授权规范
   - 9.2 数据安全规范
   - 9.3 API安全规范
   - 9.4 AI安全规范
10. **日志与监控规范**
    - 10.1 日志规范
    - 10.2 指标规范
    - 10.3 告警规范
11. **发布与部署规范**
    - 11.1 版本号规范
    - 11.2 容器镜像规范
    - 11.3 K8s资源规范
    - 11.4 灰度发布规范

------

## 1. 规范概述

### 1.1 规范目的

本规范旨在：

- 统一项目开发标准，提高代码可读性和可维护性
- 降低团队协作成本，减少沟通障碍
- 保证代码质量和系统稳定性
- 加速新成员上手速度

### 1.2 规范原则





| 原则         | 说明                                     |
| :----------- | :--------------------------------------- |
| **一致性**   | 同一类型的代码保持一致的风格和结构       |
| **可读性**   | 代码首先是给人读的，其次才是给机器执行的 |
| **简洁性**   | 保持简单，避免过度设计                   |
| **可测试性** | 代码设计应考虑可测试性                   |
| **可观测性** | 关键路径必须有日志、指标、追踪           |

### 1.3 规范等级





| 等级     | 标识       | 说明                               | 约束力 |
| :------- | :--------- | :--------------------------------- | :----- |
| **必须** | **MUST**   | 强制执行，违反将导致代码审查不通过 | 强制   |
| **推荐** | **SHOULD** | 强烈建议遵循，特殊情况可豁免       | 建议   |
| **可选** | **MAY**    | 可根据实际情况选择                 | 参考   |

### 1.4 规范更新机制

- 规范由架构组维护，每季度评审一次
- 任何人可提出修改建议，需经过架构组评审
- 规范变更需在团队内公示，并提供迁移指南

------

## 2. 代码规范

### 2.1 Python代码规范

#### 2.1.1 代码风格





| 规范项       | 要求                                                | 等级 | 工具       |
| :----------- | :-------------------------------------------------- | :--- | :--------- |
| **行长度**   | **MUST** 不超过120字符                              | 必须 | ruff       |
| **缩进**     | **MUST** 使用4个空格，禁止Tab                       | 必须 | ruff       |
| **引号**     | **SHOULD** 字符串使用双引号，文档字符串使用三双引号 | 推荐 | ruff       |
| **导入顺序** | **MUST** 标准库 → 第三方库 → 本地模块，每组间空一行 | 必须 | ruff/isort |
| **类型注解** | **MUST** 所有公共函数必须有类型注解                 | 必须 | mypy       |
| **空行**     | **SHOULD** 类定义间空2行，方法间空1行               | 推荐 | ruff       |

#### 2.1.2 命名规范





| 类型          | 规范          | 示例                                 | 等级 |
| :------------ | :------------ | :----------------------------------- | :--- |
| **模块**      | 小写+下划线   | `selection_service.py`               | 必须 |
| **类**        | 大驼峰        | `SelectionMasterAgent`               | 必须 |
| **函数/方法** | 小写+下划线   | `get_selection_task()`               | 必须 |
| **变量**      | 小写+下划线   | `task_id`, `user_list`               | 必须 |
| **常量**      | 全大写+下划线 | `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT` | 必须 |
| **私有成员**  | 单下划线前缀  | `_internal_method`, `_private_var`   | 推荐 |
| **内部私有**  | 双下划线前缀  | `__very_private`                     | 可选 |

#### 2.1.3 代码结构

python

```
# 文件头
"""
模块说明：选品任务服务
作者：张三
创建日期：2026-01-01
"""

# 标准库导入
import asyncio
from typing import Optional, List
from datetime import datetime

# 第三方库导入
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

# 本地模块导入
from src.core.database import get_db
from src.models.selection import SelectionTask
from src.schemas.selection import SelectionTaskResponse

# 常量定义
MAX_BATCH_SIZE = 100
DEFAULT_PAGE_SIZE = 20

# 类定义
class SelectionService:
    """选品服务类
    
    负责选品任务的创建、查询、更新等操作。
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_task(
        self,
        user_id: str,
        target_market: str,
        category: str,
        target_roi: float
    ) -> SelectionTask:
        """创建选品任务
        
        Args:
            user_id: 用户ID
            target_market: 目标市场 (US/EU/JP)
            category: 品类
            target_roi: 目标ROI
            
        Returns:
            创建的选品任务对象
            
        Raises:
            ValueError: 参数无效时抛出
        """
        # 参数校验
        if target_roi <= 0:
            raise ValueError("target_roi must be positive")
        
        # 创建任务
        task = SelectionTask(
            user_id=user_id,
            target_market=target_market,
            category=category,
            target_roi=target_roi,
            status="pending"
        )
        
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        
        return task

# 函数定义
async def get_selection_task(
    task_id: str,
    db: AsyncSession
) -> Optional[SelectionTask]:
    """获取选品任务
    
    Args:
        task_id: 任务ID
        db: 数据库会话
        
    Returns:
        选品任务对象，不存在返回None
    """
    return await db.get(SelectionTask, task_id)
```



#### 2.1.4 异步编程规范





| 规范项       | 要求                                    | 等级 |
| :----------- | :-------------------------------------- | :--- |
| **异步函数** | 使用 `async def` 定义                   | 必须 |
| **异步调用** | 使用 `await` 调用异步函数               | 必须 |
| **并发**     | 使用 `asyncio.gather()` 并发执行        | 推荐 |
| **阻塞操作** | 禁止在异步函数中调用同步阻塞函数        | 必须 |
| **超时**     | 异步操作应设置超时 `asyncio.wait_for()` | 推荐 |

python

```
# 正确示例
async def fetch_all_data():
    tasks = [
        fetch_amazon_data(),
        fetch_tiktok_data(),
        fetch_1688_data()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

# 错误示例
async def bad_example():
    # 禁止：同步阻塞调用
    time.sleep(5)  # 应使用 await asyncio.sleep(5)
    
    # 禁止：在循环中串行等待
    results = []
    for url in urls:
        result = await fetch(url)  # 应使用 asyncio.gather
        results.append(result)
```



#### 2.1.5 异常处理规范





| 规范项         | 要求                               | 等级 |
| :------------- | :--------------------------------- | :--- |
| **异常捕获**   | 捕获具体异常，禁止裸`except:`      | 必须 |
| **异常传播**   | 明确是否向上传播或处理             | 必须 |
| **自定义异常** | 继承`Exception`，命名以`Error`结尾 | 推荐 |
| **异常日志**   | 记录异常堆栈信息                   | 必须 |
| **资源清理**   | 使用`async with`或`try-finally`    | 必须 |

python

```
# 正确示例
class SelectionNotFoundError(Exception):
    """选品任务不存在异常"""
    pass

async def get_task(task_id: str) -> Task:
    try:
        task = await db.get(Task, task_id)
        if not task:
            raise SelectionNotFoundError(f"Task {task_id} not found")
        return task
    except SelectionNotFoundError:
        raise  # 向上传播
    except Exception as e:
        logger.error(f"Failed to get task {task_id}: {e}", exc_info=True)
        raise ServiceError("Internal service error") from e
```



#### 2.1.6 类型注解规范

python

```
from typing import Optional, List, Dict, Union, Any, TypeVar, Generic

T = TypeVar("T")

class Repository(Generic[T]):
    """泛型仓储类"""
    
    async def find_by_id(self, id: str) -> Optional[T]:
        """根据ID查询"""
        ...
    
    async def find_all(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20
    ) -> List[T]:
        """分页查询"""
        ...

# 复杂类型使用 TypeAlias
SelectionResult = Dict[str, Union[str, float, List[str]]]

def process_result(result: SelectionResult) -> float:
    """处理选品结果"""
    ...
```



### 2.2 TypeScript/JavaScript代码规范

#### 2.2.1 代码风格





| 规范项       | 要求                                | 等级 | 工具       |
| :----------- | :---------------------------------- | :--- | :--------- |
| **行长度**   | **MUST** 不超过100字符              | 必须 | ESLint     |
| **缩进**     | **MUST** 使用2个空格                | 必须 | Prettier   |
| **引号**     | **MUST** 字符串使用单引号           | 必须 | Prettier   |
| **分号**     | **MUST** 语句末尾加分号             | 必须 | ESLint     |
| **类型注解** | **MUST** 所有函数参数和返回值有类型 | 必须 | TypeScript |

#### 2.2.2 命名规范





| 类型     | 规范                | 示例                                | 等级 |
| :------- | :------------------ | :---------------------------------- | :--- |
| **文件** | 小写+连字符         | `selection-service.ts`              | 必须 |
| **组件** | 大驼峰              | `SelectionTaskList.tsx`             | 必须 |
| **函数** | 小驼峰              | `getSelectionTask`                  | 必须 |
| **变量** | 小驼峰              | `taskId`, `userList`                | 必须 |
| **常量** | 全大写+下划线       | `MAX_RETRY_COUNT`                   | 必须 |
| **接口** | 大驼峰，`I`前缀可选 | `ISelectionTask` 或 `SelectionTask` | 推荐 |
| **类型** | 大驼峰，`T`前缀可选 | `TSelectionStatus`                  | 推荐 |
| **枚举** | 大驼峰，成员全大写  | `TaskStatus.PENDING`                | 必须 |

#### 2.2.3 React组件规范

typescript

```
// 组件文件结构
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

// 类型定义
interface SelectionTaskProps {
  taskId: string;
  onAdopt?: (taskId: string) => void;
  onReject?: (taskId: string, reason: string) => void;
}

interface SelectionTaskState {
  loading: boolean;
  error: Error | null;
  task: SelectionTask | null;
}

// 组件定义
export const SelectionTaskDetail: React.FC<SelectionTaskProps> = ({
  taskId,
  onAdopt,
  onReject,
}) => {
  // Hooks（按顺序：state, query, context, ref, effect）
  const [state, setState] = useState<SelectionTaskState>({
    loading: false,
    error: null,
    task: null,
  });
  
  // 数据查询
  const { data, isLoading, error } = useQuery({
    queryKey: ['selectionTask', taskId],
    queryFn: () => fetchSelectionTask(taskId),
  });
  
  // 事件处理
  const handleAdopt = useCallback(() => {
    onAdopt?.(taskId);
  }, [taskId, onAdopt]);
  
  const handleReject = useCallback((reason: string) => {
    onReject?.(taskId, reason);
  }, [taskId, onReject]);
  
  // 渲染
  if (isLoading) {
    return <LoadingSpinner />;
  }
  
  if (error) {
    return <ErrorMessage error={error} />;
  }
  
  return (
    <div className="selection-task-detail">
      <TaskHeader task={data} />
      <TaskContent task={data} />
      <TaskActions onAdopt={handleAdopt} onReject={handleReject} />
    </div>
  );
};

// 默认导出
export default SelectionTaskDetail;
```



#### 2.2.4 Hooks规范





| 规范项          | 要求             | 等级 |
| :-------------- | :--------------- | :--- |
| **命名**        | 以`use`开头      | 必须 |
| **调用位置**    | 只在组件顶层调用 | 必须 |
| **依赖数组**    | 完整声明所有依赖 | 必须 |
| **自定义Hooks** | 单一职责，可复用 | 推荐 |

typescript

```
// 自定义Hook示例
export const useSelectionTask = (taskId: string) => {
  const [task, setTask] = useState<SelectionTask | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  
  useEffect(() => {
    let cancelled = false;
    
    const fetchTask = async () => {
      try {
        setLoading(true);
        const data = await api.getSelectionTask(taskId);
        if (!cancelled) {
          setTask(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err as Error);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    
    fetchTask();
    
    return () => {
      cancelled = true;
    };
  }, [taskId]);
  
  return { task, loading, error };
};
```



### 2.3 SQL代码规范

#### 2.3.1 书写规范





| 规范项        | 要求                     | 等级 |
| :------------ | :----------------------- | :--- |
| **关键字**    | 全大写                   | 必须 |
| **表名/列名** | 小写+下划线              | 必须 |
| **缩进**      | 子句缩进2空格            | 推荐 |
| **别名**      | 使用AS关键字             | 推荐 |
| **JOIN**      | 明确使用INNER/LEFT/RIGHT | 必须 |

sql

```
-- 正确示例
SELECT
    t.id,
    t.target_market,
    t.category,
    t.status,
    u.username AS created_by
FROM selection_tasks t
INNER JOIN users u ON t.user_id = u.id
LEFT JOIN recommendations r ON t.id = r.task_id
WHERE t.tenant_id = :tenant_id
    AND t.created_at >= :start_date
    AND t.status IN ('pending', 'running')
ORDER BY t.created_at DESC
LIMIT :limit OFFSET :offset;
```



#### 2.3.2 性能规范





| 规范项        | 要求                        | 等级 |
| :------------ | :-------------------------- | :--- |
| **SELECT ***  | 禁止使用，明确列出字段      | 必须 |
| **WHERE条件** | 使用索引字段                | 必须 |
| **函数索引**  | 避免在WHERE中对字段使用函数 | 必须 |
| **子查询**    | 优先使用JOIN                | 推荐 |
| **批量操作**  | 使用批量INSERT/UPDATE       | 推荐 |

### 2.4 配置文件规范

#### 2.4.1 环境变量规范





| 规范项       | 要求                    | 示例               | 等级 |
| :----------- | :---------------------- | :----------------- | :--- |
| **命名**     | 全大写+下划线，服务前缀 | `SELECTION_DB_URL` | 必须 |
| **敏感信息** | 禁止硬编码，使用Secret  | `DB_PASSWORD`      | 必须 |
| **默认值**   | 提供合理默认值          | `PORT=8000`        | 推荐 |
| **文档**     | `.env.example`提供模板  | -                  | 必须 |

bash

```
# .env.example
# 应用配置
APP_NAME=pms-selection-service
APP_ENV=development
APP_PORT=8001
APP_LOG_LEVEL=INFO

# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_NAME=pms
DB_USER=pms_user
DB_PASSWORD=  # 必填，无默认值

# Redis配置
REDIS_URL=redis://localhost:6379/0
REDIS_MAX_CONNECTIONS=20

# LLM配置
LLM_PRIMARY_MODEL=qwen2.5-72b
LLM_OLLAMA_ENDPOINT=http://localhost:11434
```



#### 2.4.2 YAML配置规范

yaml

```
# 正确示例
apiVersion: apps/v1
kind: Deployment
metadata:
  name: selection-service
  namespace: pms
  labels:
    app: selection-service
    version: v1
spec:
  replicas: 3
  selector:
    matchLabels:
      app: selection-service
  template:
    metadata:
      labels:
        app: selection-service
        version: v1
    spec:
      containers:
        - name: api
          image: pms/selection-service:latest
          ports:
            - containerPort: 8001
              name: http
          env:
            - name: DB_URL
              valueFrom:
                secretKeyRef:
                  name: pms-secrets
                  key: db-url
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: 2000m
              memory: 4Gi
```



------

## 3. 项目结构规范

### 3.1 后端项目结构

text

```
service-name/
├── src/
│   ├── api/                    # API层
│   │   ├── v1/
│   │   │   ├── endpoints/      # 路由端点
│   │   │   │   ├── __init__.py
│   │   │   │   ├── tasks.py
│   │   │   │   └── agents.py
│   │   │   ├── dependencies.py # 依赖注入
│   │   │   └── router.py       # 路由注册
│   │   └── websocket/          # WebSocket处理
│   ├── core/                   # 核心模块
│   │   ├── config.py           # 配置管理
│   │   ├── database.py         # 数据库连接
│   │   ├── security.py         # 安全相关
│   │   └── exceptions.py       # 异常定义
│   ├── models/                 # ORM模型
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── selection.py
│   ├── schemas/                # Pydantic Schema
│   │   ├── __init__.py
│   │   ├── request/
│   │   └── response/
│   ├── services/               # 业务服务层
│   │   ├── __init__.py
│   │   └── selection_service.py
│   ├── agents/                 # Agent模块（如适用）
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── market_insight.py
│   ├── clients/                # 外部客户端
│   │   ├── __init__.py
│   │   └── erp_client.py
│   ├── utils/                  # 工具函数
│   │   ├── __init__.py
│   │   ├── logger.py
│   │   └── helpers.py
│   └── main.py                 # 应用入口
├── tests/                      # 测试
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── conftest.py
├── alembic/                    # 数据库迁移
│   ├── versions/
│   └── alembic.ini
├── scripts/                    # 脚本
├── Dockerfile
├── pyproject.toml
├── .env.example
└── README.md
```



### 3.2 前端项目结构

text

```
frontend/
├── app/                        # Next.js App Router
│   ├── layout.tsx
│   ├── page.tsx                # 首页
│   ├── globals.css
│   ├── selection/              # 选品模块
│   │   ├── page.tsx
│   │   ├── [taskId]/
│   │   │   └── page.tsx
│   │   └── create/
│   │       └── page.tsx
│   ├── agents/                 # Agent监控
│   ├── knowledge/              # 知识库
│   ├── reports/                # 报告中心
│   └── api/                    # Next.js API代理
├── components/                 # 公共组件
│   ├── ui/                     # 基础UI
│   ├── charts/                 # 图表组件
│   ├── agent/                  # Agent相关
│   ├── knowledge/              # 知识库相关
│   └── layout/                 # 布局组件
├── lib/                        # 工具库
│   ├── api/                    # API调用
│   ├── hooks/                  # 自定义Hooks
│   ├── stores/                 # 状态管理
│   ├── utils/                  # 工具函数
│   └── types/                  # 类型定义
├── styles/                     # 样式
├── public/                     # 静态资源
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── next.config.js
```



### 3.3 微服务命名规范





| 服务类型     | 命名格式                    | 示例                         | 等级 |
| :----------- | :-------------------------- | :--------------------------- | :--- |
| **业务服务** | `{domain}-service`          | `selection-service`          | 必须 |
| **AI服务**   | `{ai-capability}-service`   | `llm-service`, `rag-service` | 必须 |
| **数据服务** | `{data-capability}-service` | `feature-service`            | 必须 |
| **网关**     | `api-gateway`               | `api-gateway`                | 必须 |

### 3.4 包命名规范





| 语言           | 规范          | 示例                | 等级 |
| :------------- | :------------ | :------------------ | :--- |
| **Python**     | 小写+下划线   | `selection_service` | 必须 |
| **TypeScript** | 小写+连字符   | `selection-service` | 必须 |
| **Java**       | 反向域名+小写 | `com.pms.selection` | 推荐 |

------

## 4. API设计规范

### 4.1 RESTful API规范

#### 4.1.1 URL设计





| 规范项       | 要求                 | 示例                                       | 等级 |
| :----------- | :------------------- | :----------------------------------------- | :--- |
| **资源命名** | 复数名词             | `/selections`, `/agents`                   | 必须 |
| **层级关系** | 嵌套表示归属         | `/selections/{id}/recommendations`         | 推荐 |
| **分隔符**   | 连字符               | `/selection-tasks`                         | 必须 |
| **版本**     | URL路径版本          | `/api/v1/selections`                       | 必须 |
| **动作**     | 避免动词，用HTTP方法 | POST `/selections` 而非 `/createSelection` | 必须 |

#### 4.1.2 HTTP方法





| 方法       | 用途     | 幂等性 | 示例                      |
| :--------- | :------- | :----- | :------------------------ |
| **GET**    | 查询资源 | 是     | `GET /selections/{id}`    |
| **POST**   | 创建资源 | 否     | `POST /selections`        |
| **PUT**    | 全量更新 | 是     | `PUT /selections/{id}`    |
| **PATCH**  | 部分更新 | 否     | `PATCH /selections/{id}`  |
| **DELETE** | 删除资源 | 是     | `DELETE /selections/{id}` |

#### 4.1.3 响应格式

typescript

```
// 成功响应
{
  "code": 200,
  "message": "success",
  "data": { ... },
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-01-01T00:00:00Z"
}

// 列表响应
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [ ... ],
    "total": 100,
    "page": 1,
    "page_size": 20,
    "total_pages": 5
  },
  "request_id": "...",
  "timestamp": "..."
}

// 错误响应
{
  "code": 400,
  "message": "Invalid parameter",
  "error": {
    "type": "ValidationError",
    "details": [
      {
        "field": "category",
        "message": "Category is required"
      }
    ]
  },
  "request_id": "...",
  "timestamp": "..."
}
```



#### 4.1.4 分页与排序





| 参数        | 说明            | 示例                     | 默认值 |
| :---------- | :-------------- | :----------------------- | :----- |
| `page`      | 页码（从1开始） | `?page=2`                | 1      |
| `page_size` | 每页条数        | `?page_size=50`          | 20     |
| `sort`      | 排序字段和方向  | `?sort=created_at:desc`  | -      |
| `fields`    | 返回字段        | `?fields=id,name,status` | 全部   |

#### 4.1.5 过滤

text

```
GET /selections?status=pending,running
GET /selections?category=electronics
GET /selections?created_at.gte=2026-01-01
GET /selections?created_at.lte=2026-01-31
GET /selections?search=户外电源
```



### 4.2 WebSocket规范

#### 4.2.1 连接

javascript

```
// 连接URL
const ws = new WebSocket('wss://api.pms.com/ws/v1/agent/stream?token=xxx');

// 心跳
ws.send(JSON.stringify({ type: 'ping' }));
// 响应: { type: 'pong', timestamp: 1234567890 }
```



#### 4.2.2 消息格式

typescript

```
// 客户端→服务端
interface ClientMessage {
  type: 'subscribe' | 'unsubscribe' | 'intervene' | 'ping';
  payload: any;
  request_id: string;
}

// 服务端→客户端
interface ServerMessage {
  type: 'log' | 'state_update' | 'progress' | 'error' | 'pong';
  payload: any;
  timestamp: string;
}

// 示例
// Agent日志推送
{
  "type": "log",
  "payload": {
    "level": "INFO",
    "agent": "MarketInsightAgent",
    "message": "开始分析市场规模...",
    "timestamp": "2026-01-01T00:00:00Z"
  }
}
```



### 4.3 gRPC规范

#### 4.3.1 Proto文件规范

protobuf

```
syntax = "proto3";

package pms.selection.v1;

option go_package = "github.com/pms/selection/api/v1";

// 服务定义
service SelectionService {
  rpc CreateTask(CreateTaskRequest) returns (CreateTaskResponse);
  rpc GetTask(GetTaskRequest) returns (GetTaskResponse);
  rpc ListTasks(ListTasksRequest) returns (ListTasksResponse);
  rpc AdoptRecommendation(AdoptRequest) returns (AdoptResponse);
}

// 消息定义
message CreateTaskRequest {
  string user_id = 1;
  string target_market = 2;
  string category = 3;
  double target_roi = 4;
}

message CreateTaskResponse {
  string task_id = 1;
  string status = 2;
  string created_at = 3;
}
```



### 4.4 错误码规范





| 范围        | 含义       | 示例                                                         |
| :---------- | :--------- | :----------------------------------------------------------- |
| **200**     | 成功       | 200 OK, 201 Created                                          |
| **400-499** | 客户端错误 | 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found |
| **500-599** | 服务端错误 | 500 Internal Error, 503 Service Unavailable                  |

#### 4.4.1 业务错误码





| 错误码 | 说明          | HTTP状态 |
| :----- | :------------ | :------- |
| 10001  | 参数校验失败  | 400      |
| 10002  | 资源不存在    | 404      |
| 10003  | 资源已存在    | 409      |
| 10004  | 权限不足      | 403      |
| 10005  | 配额超限      | 429      |
| 20001  | 数据库错误    | 500      |
| 20002  | 外部服务错误  | 503      |
| 30001  | Agent执行失败 | 500      |
| 30002  | LLM调用失败   | 503      |
| 40001  | 数据源不可用  | 503      |

------

## 5. 数据库规范

### 5.1 表命名规范





| 类型       | 规范               | 示例                    | 等级 |
| :--------- | :----------------- | :---------------------- | :--- |
| **表名**   | 小写+下划线，复数  | `selection_tasks`       | 必须 |
| **关联表** | 两表名+下划线      | `task_agents`           | 必须 |
| **临时表** | `tmp_`前缀         | `tmp_import_data`       | 推荐 |
| **备份表** | `_backup`后缀+日期 | `tasks_backup_20260101` | 推荐 |

### 5.2 字段命名规范





| 类型         | 规范              | 示例                       | 等级 |
| :----------- | :---------------- | :------------------------- | :--- |
| **字段名**   | 小写+下划线       | `user_id`, `created_at`    | 必须 |
| **主键**     | `id`              | `id`                       | 必须 |
| **外键**     | `{关联表单数}_id` | `user_id`, `task_id`       | 必须 |
| **布尔字段** | `is_`前缀         | `is_active`, `is_deleted`  | 必须 |
| **时间字段** | `_at`后缀         | `created_at`, `updated_at` | 必须 |
| **JSON字段** | `_json`后缀       | `metadata_json`            | 推荐 |

### 5.3 索引命名规范





| 类型         | 规范                         | 示例                          | 等级 |
| :----------- | :--------------------------- | :---------------------------- | :--- |
| **普通索引** | `idx_{表名}_{字段}`          | `idx_selection_tasks_status`  | 必须 |
| **唯一索引** | `udx_{表名}_{字段}`          | `udx_users_email`             | 必须 |
| **外键索引** | `idx_{表名}_{外键}`          | `idx_selection_tasks_user_id` | 必须 |
| **复合索引** | `idx_{表名}_{字段1}_{字段2}` | `idx_tasks_tenant_status`     | 必须 |

### 5.4 SQL编写规范

#### 5.4.1 DDL规范

sql

```
-- 创建表示例
CREATE TABLE selection_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    target_market VARCHAR(50) NOT NULL,
    category VARCHAR(100) NOT NULL,
    target_roi DECIMAL(5,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- 索引
CREATE INDEX idx_selection_tasks_tenant ON selection_tasks(tenant_id);
CREATE INDEX idx_selection_tasks_user ON selection_tasks(user_id);
CREATE INDEX idx_selection_tasks_status ON selection_tasks(status);
CREATE INDEX idx_selection_tasks_created ON selection_tasks(created_at DESC);

-- 外键
ALTER TABLE selection_tasks 
ADD CONSTRAINT fk_selection_tasks_tenant 
FOREIGN KEY (tenant_id) REFERENCES tenants(id);

-- 注释
COMMENT ON TABLE selection_tasks IS '选品任务表';
COMMENT ON COLUMN selection_tasks.target_market IS '目标市场: US/EU/JP/CN';
```



#### 5.4.2 查询规范

sql

```
-- 正确：使用参数化查询
SELECT * FROM selection_tasks WHERE id = :task_id;

-- 正确：明确列出字段
SELECT id, target_market, category, status FROM selection_tasks;

-- 错误：SELECT *
SELECT * FROM selection_tasks;

-- 错误：拼接SQL
query = "SELECT * FROM tasks WHERE id = '" + task_id + "'";
```



------

## 6. Git工作流规范

### 6.1 分支策略

text

```
main
  │
  ├── develop
  │     │
  │     ├── feature/selection-api
  │     ├── feature/agent-workflow
  │     ├── bugfix/fix-timeout
  │     └── hotfix/security-patch
  │
  └── release/v1.0.0
```







| 分支        | 用途     | 命名规范             | 保护                            |
| :---------- | :------- | :------------------- | :------------------------------ |
| **main**    | 生产代码 | `main`               | 必须PR，禁止直接推送            |
| **develop** | 开发主线 | `develop`            | 必须PR                          |
| **feature** | 功能开发 | `feature/{功能描述}` | 从develop拉取，合并回develop    |
| **bugfix**  | Bug修复  | `bugfix/{问题描述}`  | 从develop拉取                   |
| **hotfix**  | 紧急修复 | `hotfix/{问题描述}`  | 从main拉取，合并回main和develop |
| **release** | 发布分支 | `release/v{版本号}`  | 从develop拉取，合并回main       |

### 6.2 Commit规范

#### 6.2.1 Commit Message格式

text

```
<type>(<scope>): <subject>

<body>

<footer>
```



#### 6.2.2 Type类型





| Type         | 说明                   |
| :----------- | :--------------------- |
| **feat**     | 新功能                 |
| **fix**      | Bug修复                |
| **docs**     | 文档更新               |
| **style**    | 代码格式（不影响功能） |
| **refactor** | 重构                   |
| **perf**     | 性能优化               |
| **test**     | 测试相关               |
| **chore**    | 构建/工具相关          |
| **ci**       | CI/CD相关              |

#### 6.2.3 示例

text

```
feat(selection): 添加选品任务创建API

- 实现POST /api/v1/selections接口
- 添加参数校验
- 添加单元测试

Closes #123

fix(agent): 修复市场洞察Agent超时问题

- 增加超时时间到60秒
- 添加重试机制

Closes #456
```



### 6.3 PR/MR规范

#### 6.3.1 PR标题

text

```
[类型] 简短描述 (#issue号)
```



示例：

- `[feat] 添加选品任务创建API (#123)`
- `[fix] 修复Agent超时问题 (#456)`

#### 6.3.2 PR描述模板

markdown

```
## 变更类型
- [ ] 新功能
- [ ] Bug修复
- [ ] 重构
- [ ] 文档更新

## 变更内容
简要描述本次变更的内容

## 测试
- [ ] 单元测试通过
- [ ] 集成测试通过
- [ ] 手动测试通过

## 检查清单
- [ ] 代码符合规范
- [ ] 添加了必要的测试
- [ ] 更新了相关文档
- [ ] 通过了CI检查

## 关联Issue
Closes #xxx
```



### 6.4 代码审查规范

#### 6.4.1 审查要点





| 类别         | 检查项                     |
| :----------- | :------------------------- |
| **功能**     | 是否符合需求、边界条件处理 |
| **代码质量** | 可读性、命名规范、注释完整 |
| **性能**     | 是否有性能问题、N+1查询    |
| **安全**     | SQL注入、XSS、敏感信息     |
| **测试**     | 测试覆盖率、测试用例质量   |

#### 6.4.2 审查流程

1. 作者提交PR，添加审查人
2. 审查人进行代码审查
3. 如有问题，添加评论，标记"Request Changes"
4. 作者修改后重新请求审查
5. 审查通过，标记"Approved"
6. 合并PR，删除功能分支

------

## 7. 测试规范

### 7.1 单元测试规范

#### 7.1.1 测试文件命名





| 规范                  | 示例                          | 等级 |
| :-------------------- | :---------------------------- | :--- |
| 测试文件以`test_`开头 | `test_selection_service.py`   | 必须 |
| 测试类以`Test`开头    | `class TestSelectionService:` | 必须 |
| 测试方法以`test_`开头 | `def test_create_task():`     | 必须 |

#### 7.1.2 测试结构（AAA模式）

python

```
def test_create_task_success(db_session):
    # Arrange - 准备测试数据
    service = SelectionService(db_session)
    user_id = "user-001"
    
    # Act - 执行测试
    task = await service.create_task(
        user_id=user_id,
        target_market="US",
        category="electronics",
        target_roi=0.3
    )
    
    # Assert - 断言结果
    assert task.id is not None
    assert task.user_id == user_id
    assert task.status == "pending"
```



#### 7.1.3 Mock规范

python

```
from unittest.mock import AsyncMock, patch

async def test_fetch_amazon_data():
    # Mock外部依赖
    mock_client = AsyncMock()
    mock_client.get_product.return_value = {"asin": "B001", "title": "Test"}
    
    with patch("src.clients.amazon.AmazonClient", return_value=mock_client):
        service = DataCollectionService()
        result = await service.fetch_amazon_data("B001")
        
        assert result["asin"] == "B001"
        mock_client.get_product.assert_called_once_with("B001")
```



#### 7.1.4 覆盖率要求





| 类型             | 覆盖率要求 | 等级 |
| :--------------- | :--------- | :--- |
| **核心业务逻辑** | ≥80%       | 必须 |
| **工具函数**     | ≥90%       | 必须 |
| **Agent代码**    | ≥70%       | 必须 |
| **总体覆盖率**   | ≥80%       | 必须 |

### 7.2 集成测试规范

python

```
@pytest.mark.integration
async def test_selection_api_integration(client, db_session):
    """测试选品API集成"""
    # 创建任务
    response = await client.post("/api/v1/selections", json={
        "target_market": "US",
        "category": "electronics",
        "target_roi": 0.3
    })
    assert response.status_code == 200
    task_id = response.json()["data"]["id"]
    
    # 查询任务
    response = await client.get(f"/api/v1/selections/{task_id}")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    
    # 触发Agent
    response = await client.post(f"/api/v1/agents/trigger", json={
        "task_id": task_id
    })
    assert response.status_code == 200
```



### 7.3 端到端测试规范

python

```
@pytest.mark.e2e
async def test_selection_flow_e2e(browser, test_user):
    """测试完整选品流程"""
    # 登录
    await browser.goto("/login")
    await browser.fill("#username", test_user.username)
    await browser.fill("#password", test_user.password)
    await browser.click("#login-btn")
    
    # 创建选品任务
    await browser.goto("/selection/create")
    await browser.select("#target_market", "US")
    await browser.fill("#category", "Outdoor Power Bank")
    await browser.fill("#target_roi", "30")
    await browser.click("#submit-btn")
    
    # 等待任务完成
    await browser.wait_for_selector(".task-completed", timeout=300000)
    
    # 查看报告
    await browser.click(".view-report")
    assert await browser.is_visible(".report-title")
```



### 7.4 性能测试规范

python

```
# locustfile.py
from locust import HttpUser, task, between

class SelectionUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def get_selections(self):
        self.client.get("/api/v1/selections")
    
    @task(1)
    def create_selection(self):
        self.client.post("/api/v1/selections", json={
            "target_market": "US",
            "category": "electronics",
            "target_roi": 0.3
        })
```



------

## 8. 文档规范

### 8.1 代码注释规范

#### 8.1.1 文件头注释

python

```
"""
模块名称：选品任务服务
功能描述：提供选品任务的创建、查询、更新等核心功能
作者：张三
创建日期：2026-01-01
修改记录：
- 2026-01-15 张三：添加批量创建功能
"""
```



#### 8.1.2 函数注释

python

```
async def create_selection_task(
    user_id: str,
    target_market: str,
    category: str,
    target_roi: float,
    budget: Optional[float] = None
) -> SelectionTask:
    """
    创建选品任务
    
    Args:
        user_id: 用户ID，UUID格式
        target_market: 目标市场，支持 US/EU/JP/CN
        category: 品类，如 electronics/outdoor
        target_roi: 目标ROI，0-1之间的小数
        budget: 预算（可选），单位USD
        
    Returns:
        创建的选品任务对象
        
    Raises:
        ValueError: 参数无效时抛出
        DatabaseError: 数据库操作失败时抛出
        
    Example:
        >>> task = await create_selection_task(
        ...     user_id="550e8400-e29b-41d4-a716-446655440000",
        ...     target_market="US",
        ...     category="electronics",
        ...     target_roi=0.3
        ... )
    """
    pass
```



### 8.2 API文档规范

#### 8.2.1 OpenAPI文档

python

```
from fastapi import APIRouter, Query, Path
from pydantic import BaseModel, Field

router = APIRouter(prefix="/selections", tags=["选品任务"])

class CreateSelectionRequest(BaseModel):
    """创建选品任务请求"""
    target_market: str = Field(
        ...,
        description="目标市场",
        enum=["US", "EU", "JP", "CN"],
        example="US"
    )
    category: str = Field(
        ...,
        description="品类",
        min_length=1,
        max_length=100,
        example="electronics"
    )
    target_roi: float = Field(
        ...,
        description="目标ROI",
        ge=0,
        le=1,
        example=0.3
    )

@router.post(
    "/",
    response_model=SelectionTaskResponse,
    summary="创建选品任务",
    description="创建一个新的选品任务，系统将自动触发Agent进行分析"
)
async def create_selection(
    request: CreateSelectionRequest,
    current_user: User = Depends(get_current_user)
):
    """
    创建选品任务
    
    - **target_market**: 目标市场，必填
    - **category**: 品类，必填
    - **target_roi**: 目标ROI，必填，0-1之间
    """
    pass
```



### 8.3 架构文档规范

#### 8.3.1 架构决策记录（ADR）

markdown

```
# ADR-001: 选择LangGraph作为Agent编排框架

## 状态
已采纳

## 背景
需要为选品系统选择一个Agent编排框架，支持：
- 复杂的有状态工作流
- 条件分支和循环
- 人工干预和断点恢复
- 并行执行

## 决策
选择LangGraph作为主要Agent编排框架

## 理由
1. 原生支持状态机和检查点
2. 提供Human-in-the-loop能力
3. 与LangChain生态集成良好
4. 支持条件分支和循环

## 备选方案
1. AutoGen：更适合对话式Agent
2. CrewAI：更适合角色化任务分解
3. 自研：开发成本高

## 影响
- 开发团队需要学习LangGraph
- 可以与其他框架（AutoGen/CrewAI）协同使用
```



### 8.4 README规范

markdown

```
# 服务名称

简要描述服务的功能和定位。

## 快速开始

### 环境要求
- Python 3.11+
- PostgreSQL 14+
- Redis 7.0+

### 安装
​```bash
pip install -e .
```



### 配置

复制 `.env.example` 为 `.env`，填写必要的配置。

### 运行

bash

```
uvicorn src.main:app --reload
```



## API文档

访问 `http://localhost:8000/docs` 查看Swagger文档。

## 测试

bash

```
pytest tests/
```



## 部署

参见 `k8s/` 目录下的部署清单。

## 贡献指南

参见 `CONTRIBUTING.md`。

## 许可证

Private - Internal Use Only

text

```
***

## 9. 安全规范

### 9.1 认证授权规范

| 规范项 | 要求 | 等级 |
| :--- | :--- | :--- |
| **密码存储** | 使用bcrypt加密，cost≥12 | 必须 |
| **Token** | JWT，有效期≤24小时 | 必须 |
| **敏感接口** | 必须经过认证 | 必须 |
| **权限校验** | 每个API必须校验权限 | 必须 |
| **租户隔离** | 所有数据查询必须带tenant_id | 必须 |

​```python
# 权限校验示例
@router.post("/selections")
async def create_selection(
    request: CreateRequest,
    current_user: User = Depends(get_current_user),
    _: bool = Depends(require_permission("selection:create"))
):
    # 租户隔离
    task = SelectionTask(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        ...
    )
```



### 9.2 数据安全规范





| 规范项       | 要求               | 等级 |
| :----------- | :----------------- | :--- |
| **敏感数据** | 禁止明文存储       | 必须 |
| **日志脱敏** | 敏感字段脱敏后输出 | 必须 |
| **传输加密** | 使用TLS 1.3        | 必须 |
| **API响应**  | PII字段脱敏        | 必须 |

python

```
# 数据脱敏示例
def mask_phone(phone: str) -> str:
    """手机号脱敏：138****5678"""
    if not phone or len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"

def mask_email(email: str) -> str:
    """邮箱脱敏：us****@example.com"""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@")
    if len(local) <= 2:
        return f"**@{domain}"
    return f"{local[:2]}****@{domain}"
```



### 9.3 API安全规范





| 规范项       | 要求              | 等级 |
| :----------- | :---------------- | :--- |
| **SQL注入**  | 使用ORM参数化查询 | 必须 |
| **XSS**      | 输出编码          | 必须 |
| **CSRF**     | 使用CSRF Token    | 推荐 |
| **限流**     | 每个API配置限流   | 必须 |
| **请求大小** | 限制请求体大小    | 必须 |

### 9.4 AI安全规范





| 规范项         | 要求                 | 等级 |
| :------------- | :------------------- | :--- |
| **Prompt注入** | 检测并拒绝恶意Prompt | 必须 |
| **输出审核**   | 过滤敏感内容         | 必须 |
| **成本控制**   | 设置Token配额        | 必须 |
| **模型隔离**   | 租户间模型调用隔离   | 推荐 |

python

```
# AI安全护栏示例
class AISecurityGuard:
    PROMPT_INJECTION_PATTERNS = [
        r"ignore\s+(previous|all)\s+instructions",
        r"system:\s*",
        r"<\|.*?\|>",
    ]
    
    async def check_prompt(self, prompt: str) -> bool:
        """检查Prompt是否安全"""
        for pattern in self.PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, prompt, re.IGNORECASE):
                logger.warning(f"Prompt injection detected: {pattern}")
                return False
        return True
    
    async def check_output(self, output: str) -> str:
        """过滤输出中的敏感内容"""
        # 敏感词过滤
        output = self.filter_sensitive_words(output)
        # PII检测和脱敏
        output = self.mask_pii(output)
        return output
```



------

## 10. 日志与监控规范

### 10.1 日志规范

#### 10.1.1 日志级别





| 级别         | 使用场景               | 示例                     |
| :----------- | :--------------------- | :----------------------- |
| **DEBUG**    | 调试信息，生产环境关闭 | 变量值、中间状态         |
| **INFO**     | 关键业务流程           | 任务创建、Agent开始/结束 |
| **WARNING**  | 可恢复的异常           | 重试、降级、超时         |
| **ERROR**    | 不可恢复的错误         | 服务调用失败、数据异常   |
| **CRITICAL** | 系统级故障             | 服务无法启动、数据库断开 |

#### 10.1.2 日志格式

json

```
{
  "timestamp": "2026-01-01T00:00:00.000Z",
  "level": "INFO",
  "service": "selection-service",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "span_id": "1234567890abcdef",
  "user_id": "user-001",
  "tenant_id": "tenant-001",
  "message": "Selection task created",
  "context": {
    "task_id": "task-001",
    "target_market": "US",
    "category": "electronics"
  }
}
```



#### 10.1.3 日志规范





| 规范项         | 要求                 | 等级 |
| :------------- | :------------------- | :--- |
| **结构化日志** | 使用JSON格式         | 必须 |
| **Trace ID**   | 每条日志包含trace_id | 必须 |
| **敏感信息**   | 禁止记录密码、Token  | 必须 |
| **日志轮转**   | 按天轮转，保留30天   | 必须 |

### 10.2 指标规范

#### 10.2.1 指标命名

text

```
{namespace}_{subsystem}_{metric}_{unit}

示例：
pms_api_request_duration_seconds
pms_llm_tokens_processed_total
pms_selection_task_status_total
```



#### 10.2.2 核心指标





| 指标名称                           | 类型      | 标签                 | 说明          |
| :--------------------------------- | :-------- | :------------------- | :------------ |
| `http_request_duration_seconds`    | Histogram | method, path, status | API请求耗时   |
| `http_requests_total`              | Counter   | method, path, status | API请求总数   |
| `llm_inference_duration_seconds`   | Histogram | model, task_type     | LLM推理耗时   |
| `llm_tokens_processed_total`       | Counter   | model, direction     | Token消耗     |
| `selection_tasks_total`            | Counter   | status               | 选品任务总数  |
| `agent_execution_duration_seconds` | Histogram | agent_name           | Agent执行耗时 |

### 10.3 告警规范





| 告警名称             | 级别 | 条件                    | 通知方式       |
| :------------------- | :--- | :---------------------- | :------------- |
| `HighAPIErrorRate`   | P1   | 错误率>5%持续5分钟      | PagerDuty+钉钉 |
| `HighAPILatency`     | P2   | P95延迟>500ms持续5分钟  | 钉钉+邮件      |
| `LLMServiceDown`     | P0   | LLM服务不可用           | PagerDuty电话  |
| `HighLLMLatency`     | P2   | LLM推理延迟>5s持续5分钟 | 钉钉           |
| `KafkaConsumerLag`   | P1   | Lag>10000持续10分钟     | PagerDuty+钉钉 |
| `HighGPUUtilization` | P2   | GPU利用率>90%持续10分钟 | 钉钉           |

------

## 11. 发布与部署规范

### 11.1 版本号规范

采用语义化版本（SemVer）：`MAJOR.MINOR.PATCH`





| 版本号    | 变更类型           | 示例          |
| :-------- | :----------------- | :------------ |
| **MAJOR** | 不兼容的API变更    | 1.0.0 → 2.0.0 |
| **MINOR** | 向后兼容的功能新增 | 1.0.0 → 1.1.0 |
| **PATCH** | 向后兼容的问题修复 | 1.0.0 → 1.0.1 |

### 11.2 容器镜像规范

#### 11.2.1 镜像命名

text

```
{registry}/{service-name}:{version}

示例：
pms-registry.pms.com/selection-service:1.0.0
pms-registry.pms.com/selection-service:latest
```



#### 11.2.2 Dockerfile规范

dockerfile

```
# 多阶段构建
FROM python:3.11-slim AS builder

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev --no-interaction --no-ansi

FROM python:3.11-slim AS runtime

# 创建非root用户
RUN groupadd -r pms && useradd -r -g pms pms

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ ./src/

# 切换到非root用户
USER pms

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```



### 11.3 K8s资源规范

#### 11.3.1 资源标签

yaml

```
metadata:
  labels:
    app.kubernetes.io/name: selection-service
    app.kubernetes.io/version: "1.0.0"
    app.kubernetes.io/part-of: pms
    app.kubernetes.io/managed-by: argocd
```



#### 11.3.2 资源配置

yaml

```
resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: 2000m
    memory: 4Gi
```



### 11.4 灰度发布规范

yaml

```
# Argo Rollouts配置
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: selection-service
spec:
  replicas: 4
  strategy:
    canary:
      steps:
        - setWeight: 5
        - pause: { duration: 30m }
        - setWeight: 25
        - pause: { duration: 2h }
        - setWeight: 100
```



------

**文档版本**: v1.0
**创建日期**: 2026-04-23
**项目代号**: Project Aegis
**文档状态**: 正式版
**维护者**: 架构组