"""
Prompt模板管理
==============

提供RAG系统的Prompt模板(D15-T052):
    - 选品分析Prompt
    - 趋势预测Prompt
    - 竞品对比Prompt
    - 通用RAG问答Prompt
    - 模板变量替换与校验

使用方式:
    from src.rag.prompts import PromptTemplate, get_selection_prompt

    prompt = get_selection_prompt()
    rendered = prompt.render(context="检索到的产品信息...", query="蓝牙耳机推荐")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptTemplate:
    """
    Prompt模板。

    支持变量占位符和条件渲染:
        - {variable}: 必填变量
        - {variable?}: 可选变量(缺失时移除整句)
        - {#section}...{/section}: 条件区块

    Attributes:
        name: 模板名称标识
        system_prompt: 系统角色定义
        user_template: 用户输入模板
        variables: 变量定义(名称/描述/是否必填/默认值)
    """

    name: str
    system_prompt: str
    user_template: str = ""
    variables: dict[str, dict[str, Any]] = field(default_factory=dict)
    version: str = "1.0"

    def render(
        self,
        **kwargs: Any,
    ) -> dict[str, str]:
        """
        渲染模板为最终Prompt。

        Args:
            **kwargs: 模板变量值

        Returns:
            dict: {"system": ..., "user": ...}

        Raises:
            ValueError: 缺少必填变量时抛出
        """
        self._validate_kwargs(kwargs)

        system = self._render_text(self.system_prompt, kwargs)

        user = self._render_text(self.user_template, kwargs) if self.user_template else kwargs.get("query", "")

        return {"system": system.strip(), "user": user.strip()}

    def _validate_kwargs(self, kwargs: dict[str, Any]):
        """校验必填变量。"""
        for var_name, var_def in self.variables.items():
            if var_def.get("required", False) and var_name not in kwargs:
                raise ValueError(
                    f"模板'{self.name}'缺少必填变量: '{var_name}' ({var_def.get('description', '')})"
                )

    def _render_text(self, text: str, kwargs: dict[str, Any]) -> str:
        """渲染文本中的变量占位符。"""
        result = text

        for var_name in list(self.variables.keys()) + list(kwargs.keys()):
            value = kwargs.get(var_name)

            optional_pattern = r"([^\n]*?)\{" + re.escape(var_name) + r"\?\}([^{}]*?(?:\n|$))"

            def replace_optional(m, val=value):
                prefix = m.group(1)
                suffix = m.group(2)
                return (prefix + str(val) + suffix) if val is not None else ""

            result = re.sub(optional_pattern, replace_optional, result)

            placeholder = "{" + var_name + "}"
            if placeholder in result:
                result = result.replace(placeholder, str(value or ""))

        block_pattern = r"\{#(\w+)\}(.*?)\{/(\w+)\}"

        def replace_block(m):
            block_name = m.group(1)
            content = m.group(2)
            end_name = m.group(3)

            if block_name != end_name:
                return m.group(0)

            condition = kwargs.get(block_name)
            return content if condition else ""

        import re as _re
        result = _re.sub(block_pattern, replace_block, result, flags=_re.DOTALL)

        result = result.replace("{", "").replace("}", "")

        while "  " in result:
            result = result.replace("  ", " ")

        return result.strip()


SELECTION_ANALYSIS_PROMPT = PromptTemplate(
    name="selection_analysis",
    version="1.0",
    system_prompt="""你是一个跨境电商AI选品专家，拥有丰富的Amazon/TikTok平台选品经验。

你的任务是基于提供的产品数据和市场信息，进行专业的选品分析。

分析原则:
1. 数据驱动: 所有结论必须有数据支撑
2. 风险意识: 明确指出潜在风险和不确定性
3. 可操作性: 给出具体的行动建议
4. 客观中立: 不夸大优点，不隐瞒缺点

输出格式:
- 市场机会评分(1-10): 综合评估
- 核心优势: 3-5个关键优势点
- 潜在风险: 3-5个风险因素
- 行动建议: 具体的下一步操作建议""",
    user_template="""请基于以下信息进行选品分析:

## 产品基本信息
{product_info?}

## 市场数据
{market_data?}

## 竞品情况
{competitor_info?}

## 用户查询
{query}

请给出详细的选品分析和建议。""",
    variables={
        "query": {"description": "用户问题或需求", "required": True},
        "product_info": {"description": "产品基本信息(ASIN/价格/类目等)", "required": False},
        "market_data": {"description": "市场数据(BSR排名/销量趋势等)", "required": False},
        "competitor_info": {"description": "竞品分析数据", "required": False},
    },
)

TREND_PREDICTION_PROMPT = PromptTemplate(
    name="trend_prediction",
    version="1.0",
    system_prompt="""你是一个电商市场趋势预测AI助手，擅长分析历史数据并预测未来走向。

预测方法论:
1. 时间序列分析: 识别季节性、周期性、趋势性
2. 因素关联: 关联外部事件(节日/政策/热点)
3. 类比推理: 参考相似品类的发展轨迹
4. 不确定性量化: 给出置信区间而非单点预测

输出要求:
- 趋势方向: 上升/下降/平稳
- 预测周期: 短期(30天)/中期(90天)/长期(180天)
- 置信度: 高/中/低，附依据
- 关键指标: 关注的核心数据点""",
    user_template="""基于以下数据预测{category}品类的市场趋势:

## 历史数据
{historical_data?}

## 当前市场状态
{current_status?}

## 外部因素
{external_factors?}

## 分析需求
{query}

请给出详细的趋势预测和分析。""",
    variables={
        "query": {"description": "预测分析的具体问题", "required": True},
        "category": {"description": "目标品类名称", "required": False, "default": "该"},
        "historical_data": {"description": "历史销量/搜索量/BSR数据", "required": False},
        "current_status": {"description": "当前市场状态快照", "required": False},
        "external_factors": {"description": "外部影响因素(节日/政策等)", "required": False},
    },
)

COMPETITOR_COMPARE_PROMPT = PromptTemplate(
    name="competitor_compare",
    version="1.0",
    system_prompt="""你是一个竞品分析AI专家，能够从多维度深度对比竞争产品。

对比维度:
1. 产品力: 功能/质量/设计/创新
2. 价格策略: 定位/折扣/性价比
3. 营销能力: Listing优化/广告投放/评论运营
4. 供应链: 库存/物流/成本控制
5. 品牌建设: 认知度/忠诚度/差异化

输出格式:
- 对比表格: 多维度打分对比
- 差异化亮点: 各产品的独特优势
- 改进建议: 针对性的优化方向""",
    user_template="""请对以下竞品进行全面对比分析:

## 目标产品
{target_product?}

## 竞品列表
{competitor_list?}

## 对比维度要求
{dimensions?}

## 用户关注点
{query}

请给出结构化的竞品对比报告。""",
    variables={
        "query": {"description": "用户关注的对比重点", "required": True},
        "target_product": {"description": "目标产品(我方产品)", "required": False},
        "competitor_list": {"description": "竞品列表(JSON格式)", "required": False},
        "dimensions": {"description": "自定义对比维度", "required": False},
    },
)

RAG_QA_PROMPT = PromptTemplate(
    name="rag_qa",
    version="1.0",
    system_prompt="""你是一个跨境电商知识库问答助手。你的回答严格基于提供的参考信息。

回答原则:
1. 准确性优先: 只回答有把握的内容
2. 引用来源: 标注信息来源(如有)
3. 结构清晰: 使用列表/表格等格式
4. 承认局限: 信息不足时明确说明

如果参考信息无法完全回答问题，请说明已知部分和未知部分。""",
    user_template="""## 参考信息
{context}

---
## 问题
{query}

请基于以上参考信息回答问题。如果信息不足，请说明。""",
    variables={
        "query": {"description": "用户问题", "required": True},
        "context": {"description": "RAG检索到的上下文片段", "required": True},
    },
)


def get_selection_prompt() -> PromptTemplate:
    """获取选品分析Prompt模板。"""
    return SELECTION_ANALYSIS_PROMPT

def get_trend_prompt() -> PromptTemplate:
    """获取趋势预测Prompt模板。"""
    return TREND_PREDICTION_PROMPT

def get_competitor_prompt() -> PromptTemplate:
    """获取竞品对比Prompt模板。"""
    return COMPETITOR_COMPARE_PROMPT

def get_rag_qa_prompt() -> PromptTemplate:
    """获取通用RAG问答Prompt模板。"""
    return RAG_QA_PROMPT

def get_prompt_by_name(name: str) -> PromptTemplate | None:
    """按名称获取Prompt模板。"""
    templates = {
        "selection_analysis": SELECTION_ANALYSIS_PROMPT,
        "trend_prediction": TREND_PREDICTION_PROMPT,
        "competitor_compare": COMPETITOR_COMPARE_PROMPT,
        "rag_qa": RAG_QA_PROMPT,
    }
    return templates.get(name)
