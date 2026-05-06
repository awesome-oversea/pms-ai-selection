# Agent框架启动方案

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术设计文档
> **子任务**: D21-D23 Agent框架启动
> **文档版本**: v1.0

---

## 目录

- [1. 概述](#1-概述)
- [2. LangGraph框架集成](#2-langgraph框架集成)
- [3. AutoGen框架集成](#3-autogen框架集成)
- [4. Selection Master状态机](#4-selection-master状态机)
- [5. Agent角色定义](#5-agent角色定义)

---

## 1. 概述

### 1.1 设计目标

集成Multi-Agent框架，设计并实现选品系统的核心状态机，定义Agent角色和协作机制。

### 1.2 框架选型

| 框架 | 用途 | 特点 |
|------|------|------|
| LangGraph | 状态机编排 | 有向图、条件分支、循环 |
| AutoGen | 多Agent对话 | 角色定义、消息传递 |

---

## 2. LangGraph框架集成

### 2.1 框架架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph架构                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    StateGraph                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 节点定义  │ │ 边定义   │ │ 条件边   │               │   │
│  │  │ (Node)   │ │ (Edge)   │ │ (Cond)   │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    状态管理                              │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ State    │ │ Context  │ │ Memory   │               │   │
│  │  │ 定义     │ │ 传递     │ │ 持久化   │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    执行引擎                              │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 调度器   │ │ 检查点   │ │ 回溯     │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 状态定义

```python
from typing import TypedDict, List, Dict, Any, Optional
from enum import Enum

class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class SelectionState(TypedDict):
    query: str
    user_id: str
    task_id: str
    
    market_data: Dict[str, Any]
    competitor_data: Dict[str, Any]
    product_definition: Dict[str, Any]
    commercial_report: Dict[str, Any]
    
    current_agent: str
    agent_status: Dict[str, AgentStatus]
    agent_outputs: Dict[str, Any]
    
    iteration_count: int
    max_iterations: int
    
    errors: List[Dict[str, Any]]
    warnings: List[str]
    
    human_approval_required: bool
    human_approved: Optional[bool]
    human_feedback: Optional[str]
```

### 2.3 图定义

```python
from langgraph.graph import StateGraph, END

def create_selection_graph():
    graph = StateGraph(SelectionState)
    
    graph.add_node("data_collection", data_collection_node)
    graph.add_node("market_analysis", market_analysis_node)
    graph.add_node("product_planning", product_planning_node)
    graph.add_node("commercial_analysis", commercial_analysis_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("finalize", finalize_node)
    
    graph.set_entry_point("data_collection")
    
    graph.add_edge("data_collection", "market_analysis")
    
    graph.add_conditional_edges(
        "market_analysis",
        should_continue_after_market_analysis,
        {
            "continue": "product_planning",
            "retry": "data_collection",
            "abort": END
        }
    )
    
    graph.add_conditional_edges(
        "product_planning",
        should_continue_after_product_planning,
        {
            "continue": "commercial_analysis",
            "retry": "market_analysis",
            "abort": END
        }
    )
    
    graph.add_conditional_edges(
        "commercial_analysis",
        should_continue_after_commercial,
        {
            "continue": "human_review",
            "retry": "product_planning",
            "abort": END
        }
    )
    
    graph.add_conditional_edges(
        "human_review",
        process_human_feedback,
        {
            "approved": "finalize",
            "rejected": "product_planning",
            "feedback": "market_analysis"
        }
    )
    
    graph.add_edge("finalize", END)
    
    return graph.compile()
```

### 2.4 节点实现

```python
async def data_collection_node(state: SelectionState) -> SelectionState:
    state["current_agent"] = "DataCollector"
    state["agent_status"]["DataCollector"] = AgentStatus.RUNNING
    
    try:
        data_collector = DataCollectionAgent()
        
        market_data = await data_collector.collect(
            query=state["query"],
            sources=["amazon", "tiktok", "google_trends", "1688"]
        )
        
        state["market_data"] = market_data
        state["agent_status"]["DataCollector"] = AgentStatus.COMPLETED
        state["agent_outputs"]["DataCollector"] = market_data
        
    except Exception as e:
        state["agent_status"]["DataCollector"] = AgentStatus.FAILED
        state["errors"].append({
            "agent": "DataCollector",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })
    
    return state

async def market_analysis_node(state: SelectionState) -> SelectionState:
    state["current_agent"] = "MarketAnalyst"
    state["agent_status"]["MarketAnalyst"] = AgentStatus.RUNNING
    
    try:
        market_analyst = MarketInsightAgent()
        
        analysis = await market_analyst.analyze(
            market_data=state["market_data"],
            query=state["query"]
        )
        
        state["competitor_data"] = analysis.get("competitors", {})
        state["agent_status"]["MarketAnalyst"] = AgentStatus.COMPLETED
        state["agent_outputs"]["MarketAnalyst"] = analysis
        
    except Exception as e:
        state["agent_status"]["MarketAnalyst"] = AgentStatus.FAILED
        state["errors"].append({
            "agent": "MarketAnalyst",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })
    
    return state
```

### 2.5 条件边实现

```python
def should_continue_after_market_analysis(state: SelectionState) -> str:
    if state["agent_status"]["MarketAnalyst"] == AgentStatus.FAILED:
        if state["iteration_count"] < state["max_iterations"]:
            state["iteration_count"] += 1
            return "retry"
        return "abort"
    
    market_data = state.get("market_data", {})
    
    if not market_data.get("products"):
        state["warnings"].append("市场数据不足，需要重新采集")
        return "retry"
    
    if market_data.get("market_size", 0) < 100000:
        state["warnings"].append("市场规模过小，建议终止")
        return "abort"
    
    return "continue"

def should_continue_after_product_planning(state: SelectionState) -> str:
    if state["agent_status"]["ProductPlanner"] == AgentStatus.FAILED:
        if state["iteration_count"] < state["max_iterations"]:
            state["iteration_count"] += 1
            return "retry"
        return "abort"
    
    product_def = state.get("product_definition", {})
    
    if not product_def.get("recommended_products"):
        state["warnings"].append("未找到合适的产品建议")
        return "retry"
    
    return "continue"

def process_human_feedback(state: SelectionState) -> str:
    if state.get("human_approved") is True:
        return "approved"
    elif state.get("human_approved") is False:
        return "rejected"
    elif state.get("human_feedback"):
        return "feedback"
    
    return "approved"
```

---

## 3. AutoGen框架集成

### 3.1 Agent定义

```python
import autogen

class AgentConfig:
    def __init__(self, llm_config: dict):
        self.llm_config = llm_config
    
    def create_coordinator(self):
        return autogen.AssistantAgent(
            name="Coordinator",
            system_message="""你是一个选品协调员，负责协调各个专家Agent完成选品任务。
            你需要：
            1. 理解用户需求
            2. 分配任务给合适的专家
            3. 汇总各专家的分析结果
            4. 给出最终建议""",
            llm_config=self.llm_config
        )
    
    def create_data_collector(self):
        return autogen.AssistantAgent(
            name="DataCollector",
            system_message="""你是一个数据采集专家，负责从多个数据源采集市场数据。
            你可以使用以下工具：
            - Amazon API: 获取商品和评论数据
            - TikTok API: 获取社交媒体趋势
            - Google Trends API: 获取搜索趋势
            - 1688 API: 获取供应商信息""",
            llm_config=self.llm_config
        )
    
    def create_market_analyst(self):
        return autogen.AssistantAgent(
            name="MarketAnalyst",
            system_message="""你是一个市场分析专家，负责分析市场趋势和竞争格局。
            你需要：
            1. 分析市场规模和增长趋势
            2. 识别主要竞争对手
            3. 评估市场机会和风险""",
            llm_config=self.llm_config
        )
    
    def create_product_planner(self):
        return autogen.AssistantAgent(
            name="ProductPlanner",
            system_message="""你是一个产品规划专家，负责制定产品策略。
            你需要：
            1. 分析用户需求和痛点
            2. 定义产品差异化策略
            3. 制定产品规格和定价""",
            llm_config=self.llm_config
        )
    
    def create_commercial_analyst(self):
        return autogen.AssistantAgent(
            name="CommercialAnalyst",
            system_message="""你是一个商业化分析专家，负责评估商业可行性。
            你需要：
            1. 计算成本和利润
            2. 评估ROI
            3. 给出定价建议""",
            llm_config=self.llm_config
        )
```

### 3.2 对话协议

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class AgentMessage(BaseModel):
    message_id: str
    conversation_id: str
    
    from_agent: str
    to_agent: str
    
    message_type: str
    content: dict
    
    timestamp: datetime = datetime.now()
    
    parent_message_id: Optional[str] = None
    reply_to: Optional[str] = None

class MessageProtocol:
    MESSAGE_TYPES = {
        "task_assignment": "任务分配",
        "task_result": "任务结果",
        "query": "查询请求",
        "response": "查询响应",
        "approval_request": "审批请求",
        "approval_response": "审批响应",
        "error": "错误报告",
        "status_update": "状态更新"
    }
    
    @staticmethod
    def create_task_assignment(
        from_agent: str,
        to_agent: str,
        task: dict,
        conversation_id: str
    ) -> AgentMessage:
        return AgentMessage(
            message_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message_type="task_assignment",
            content={"task": task}
        )
    
    @staticmethod
    def create_task_result(
        from_agent: str,
        to_agent: str,
        result: dict,
        conversation_id: str,
        parent_message_id: str
    ) -> AgentMessage:
        return AgentMessage(
            message_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message_type="task_result",
            content={"result": result},
            parent_message_id=parent_message_id
        )
```

### 3.3 群组对话

```python
class AgentGroupChat:
    def __init__(self, agents: list, max_rounds: int = 10):
        self.agents = agents
        self.max_rounds = max_rounds
        self.message_history = []
    
    async def run(self, initial_message: str) -> dict:
        user_proxy = autogen.UserProxyAgent(
            name="User",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=0
        )
        
        groupchat = autogen.GroupChat(
            agents=self.agents + [user_proxy],
            messages=[],
            max_round=self.max_rounds
        )
        
        manager = autogen.GroupChatManager(
            groupchat=groupchat,
            llm_config=self.agents[0].llm_config
        )
        
        await user_proxy.initiate_chat(
            manager,
            message=initial_message
        )
        
        return {
            "messages": groupchat.messages,
            "rounds": len(groupchat.messages)
        }
```

---

## 4. Selection Master状态机

### 4.1 状态流转图

```
┌─────────────────────────────────────────────────────────────────┐
│                    Selection Master状态机                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   START ──→ 数据采集 ──→ 市场分析 ──→ 产品规划 ──→ 商业化 ──→ END │
│               │            │            │            │          │
│               │            │            │            │          │
│               ▼            ▼            ▼            ▼          │
│           [数据不足]   [市场不行]   [产品不优]   [ROI不达标]     │
│               │            │            │            │          │
│               ▼            ▼            ▼            ▼          │
│           数据采集     终止流程     产品规划     商业化          │
│                                                                 │
│                          │                                      │
│                          ▼                                      │
│                     人工审批节点                                 │
│                          │                                      │
│              ┌───────────┼───────────┐                         │
│              ▼           ▼           ▼                         │
│           [通过]      [拒绝]      [反馈]                       │
│              │           │           │                         │
│              ▼           ▼           ▼                         │
│            完成       产品规划    市场分析                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 状态机配置

```yaml
state_machine:
  name: SelectionMaster
  
  states:
    - name: START
      type: initial
    
    - name: DATA_COLLECTION
      agent: DataCollector
      timeout: 300
      retry: 3
    
    - name: MARKET_ANALYSIS
      agent: MarketAnalyst
      timeout: 300
      retry: 3
    
    - name: PRODUCT_PLANNING
      agent: ProductPlanner
      timeout: 300
      retry: 3
    
    - name: COMMERCIAL_ANALYSIS
      agent: CommercialAnalyst
      timeout: 300
      retry: 3
    
    - name: HUMAN_REVIEW
      type: human
      timeout: 3600
    
    - name: FINALIZE
      type: final
    
    - name: END
      type: terminal
  
  transitions:
    - from: START
      to: DATA_COLLECTION
    
    - from: DATA_COLLECTION
      to: MARKET_ANALYSIS
      condition: data_sufficient
    
    - from: DATA_COLLECTION
      to: DATA_COLLECTION
      condition: data_insufficient
    
    - from: MARKET_ANALYSIS
      to: PRODUCT_PLANNING
      condition: market_viable
    
    - from: MARKET_ANALYSIS
      to: END
      condition: market_not_viable
    
    - from: PRODUCT_PLANNING
      to: COMMERCIAL_ANALYSIS
      condition: product_defined
    
    - from: PRODUCT_PLANNING
      to: MARKET_ANALYSIS
      condition: need_more_analysis
    
    - from: COMMERCIAL_ANALYSIS
      to: HUMAN_REVIEW
      condition: roi_acceptable
    
    - from: COMMERCIAL_ANALYSIS
      to: PRODUCT_PLANNING
      condition: roi_not_acceptable
    
    - from: HUMAN_REVIEW
      to: FINALIZE
      condition: approved
    
    - from: HUMAN_REVIEW
      to: PRODUCT_PLANNING
      condition: rejected
    
    - from: FINALIZE
      to: END
```

---

## 5. Agent角色定义

### 5.1 角色矩阵

| Agent | 角色 | 职责 | 工具 | 输入 | 输出 |
|-------|------|------|------|------|------|
| Coordinator | 协调员 | 任务分解、结果汇总 | 无 | 用户查询 | 最终报告 |
| DataCollector | 数据采集 | 多源数据采集 | Amazon/TikTok/Google/1688 API | 查询关键词 | 市场数据 |
| MarketAnalyst | 市场分析 | 趋势/竞品分析 | RAG/统计模型 | 市场数据 | 分析报告 |
| ProductPlanner | 产品规划 | 产品定义/差异化 | LLM/知识库 | 分析报告 | 产品方案 |
| CommercialAnalyst | 商业分析 | 成本/利润/ROI | 计算模型 | 产品方案 | 商业报告 |

### 5.2 Agent基类

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseAgent(ABC):
    def __init__(self, name: str, llm_client, tools: list = None):
        self.name = name
        self.llm = llm_client
        self.tools = tools or []
        self.memory = []
    
    @abstractmethod
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    def add_to_memory(self, message: Dict[str, Any]):
        self.memory.append(message)
    
    def get_context(self) -> str:
        return "\n".join([
            f"{m['role']}: {m['content']}"
            for m in self.memory[-10:]
        ])
    
    async def use_tool(self, tool_name: str, **kwargs) -> Any:
        for tool in self.tools:
            if tool.name == tool_name:
                return await tool.execute(**kwargs)
        raise ValueError(f"Tool not found: {tool_name}")
```

### 5.3 具体Agent实现

```python
class DataCollectionAgent(BaseAgent):
    def __init__(self, llm_client, tools: list):
        super().__init__("DataCollector", llm_client, tools)
    
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        query = state["query"]
        
        amazon_data = await self.use_tool(
            "amazon_api",
            query=query,
            max_results=100
        )
        
        tiktok_data = await self.use_tool(
            "tiktok_api",
            query=query,
            max_results=50
        )
        
        trends_data = await self.use_tool(
            "google_trends",
            query=query
        )
        
        supplier_data = await self.use_tool(
            "alibaba_api",
            query=query,
            max_results=30
        )
        
        return {
            "market_data": {
                "amazon": amazon_data,
                "tiktok": tiktok_data,
                "trends": trends_data,
                "suppliers": supplier_data
            }
        }

class MarketInsightAgent(BaseAgent):
    def __init__(self, llm_client, tools: list):
        super().__init__("MarketAnalyst", llm_client, tools)
    
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        market_data = state["market_data"]
        query = state["query"]
        
        prompt = f"""
        分析以下市场数据，回答问题：{query}
        
        数据：
        {json.dumps(market_data, ensure_ascii=False, indent=2)}
        
        请提供：
        1. 市场规模估算
        2. 增长趋势分析
        3. 竞争格局分析
        4. 机会和风险评估
        """
        
        analysis = await self.llm.generate(prompt)
        
        return {
            "analysis": analysis,
            "competitors": self._extract_competitors(market_data)
        }
```

---

## 附录

### A. 验收检查清单

```markdown
## D21-D23 验收检查清单

### LangGraph
- [ ] 框架依赖安装
- [ ] StateGraph创建成功
- [ ] 节点定义正确
- [ ] 条件边工作正常
- [ ] 状态持久化配置

### AutoGen
- [ ] 框架初始化
- [ ] Agent创建成功
- [ ] 对话协议定义
- [ ] 群组对话测试

### Selection Master
- [ ] 状态机定义完整
- [ ] 状态流转正确
- [ ] 条件判断准确
- [ ] 循环/重试机制

### Agent角色
- [ ] 四Agent角色定义
- [ ] 工具绑定正确
- [ ] 输入输出格式
```

### B. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
