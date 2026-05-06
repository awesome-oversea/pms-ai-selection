from __future__ import annotations

from src.agents.report_generator import ReportGeneratorAgent


def test_report_generator_data_collection_section_surfaces_governance_and_supply_counts():
    agent = ReportGeneratorAgent()

    sections = agent._build_sections(
        {
            "data_collection": {
                "quality_report": {"validity_rate": 0.93},
                "requested_mode": "auto",
                "runtime_mode": "degraded",
                "degraded": True,
                "amazon_data": {
                    "bsr": {
                        "products": [{"asin": "A1"}, {"asin": "A2"}],
                    }
                },
                "tiktok_data": {
                    "products": {
                        "products": [{"product_id": "TK1"}],
                    }
                },
                "trend_data": {
                    "trend_data": {
                        "portable blender": {"avg_interest": 78},
                        "mini juicer": {"avg_interest": 65},
                    }
                },
                "supply_chain_data": {
                    "suppliers": [{"supplier_id": "SUP-1"}],
                },
                "external_signal_summary": {
                    "has_external_signal_fallbacks": True,
                    "fallback_tool_count": 2,
                    "fallback_business_sources": ["amazon", "ali1688"],
                    "local_validation_only_sources": ["amazon", "ali1688"],
                },
            }
        }
    )

    assert sections
    data_section = sections[0]
    assert data_section.section_id == "data_collection"
    assert "Amazon候选 2" in data_section.content
    assert "TikTok商品 1" in data_section.content
    assert "Google关键词 2" in data_section.content
    assert "1688供应商 1" in data_section.content
    assert "运行模式: degraded" in data_section.content
    assert "信号治理: 当前仅达到本地业务验证可用" in data_section.content
    assert "external signal fallback 2 个工具 / 2 个业务源" in data_section.content
    assert "本地验证来源: amazon, ali1688" in data_section.content
