"""
数据清洗ETL Pipeline
====================

提供采集数据的清洗与转换能力(D12-T043/T044):
    - 去重逻辑(ASIN+日期唯一键)
    - 格式归一化(价格/评分标准化)
    - 异常值剔除(价格<0或>99999)
    - 数据质量评分
    - Flink集成接口

使用方式:
    from src.services.etl import ETLPipeline

    pipeline = ETLPipeline()
    cleaned = pipeline.clean_products(raw_data, source="amazon_bsr")
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class DataQualityRule:
    """
    数据质量校验规则。

    每条规则定义一个检查项和对应的修复策略。
    """

    def __init__(
        self,
        name: str,
        validator: Any,
        severity: str = "error",
        fixable: bool = False,
    ):
        self.name = name
        self.validator = validator
        self.severity = severity
        self.fixable = fixable


class DataQualityReport:
    """
    数据质量报告。

    记录ETL处理过程中的统计数据:
        - 输入/输出记录数
        - 各规则通过率
        - 错误详情
    """

    def __init__(self):
        self.input_count: int = 0
        self.output_count: int = 0
        self.dropped_count: int = 0
        self.dedup_count: int = 0
        self.rule_results: dict[str, dict] = {}
        self.errors: list[dict] = []
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None

    def start(self):
        self.start_time = datetime.now()

    def finish(self):
        self.end_time = datetime.now()

    @property
    def pass_rate(self) -> float:
        if self.input_count == 0:
            return 1.0
        return self.output_count / self.input_count

    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_count": self.input_count,
            "output_count": self.output_count,
            "dropped_count": self.dropped_count,
            "dedup_count": self.dedup_count,
            "pass_rate": round(self.pass_rate * 100, 2),
            "duration_seconds": round(self.duration_seconds, 3),
            "rule_results": self.rule_results,
            "error_count": len(self.errors),
        }


class ETLPipeline:
    """
    ETL数据处理管道(D12-T043)。

    处理流程:
        1. Extract: 接收原始采集数据
        2. Transform: 清洗/标准化/去重
        3. Load: 输出干净数据(可写入DB/Kafka/Qdrant)

    支持的数据源:
        - amazon_bsr: BSR排行榜数据
        - amazon_review: 评论数据
        - tiktok_data: TikTok电商数据
    """

    def __init__(self):
        self.rules = self._build_rules()
        self._seen_hashes: set[str] = set()
        self.report = DataQualityReport()

    def _build_rules(self) -> list[DataQualityRule]:
        """构建默认数据质量规则集。"""
        return [
            DataQualityRule(
                name="asin_format_valid",
                validator=lambda d: bool(
                    d.get("asin") and
                    len(str(d["asin"])) == 10 and
                    str(d["asin"]).isalnum()
                ),
                severity="error",
            ),
            DataQualityRule(
                name="price_in_range",
                validator=lambda d: (
                    d.get("price") is None or
                    (0 < float(d["price"]) <= 99999)
                ),
                severity="error",
            ),
            DataQualityRule(
                name="rating_in_range",
                validator=lambda d: (
                    d.get("rating") is None or
                    (0 <= float(d["rating"]) <= 5)
                ),
                severity="error",
            ),
            DataQualityRule(
                name="has_name",
                validator=lambda d: bool(
                    d.get("name") and len(str(d["name"]).strip()) >= 2
                ),
                severity="warning",
                fixable=True,
            ),
            DataQualityRule(
                name="review_count_non_negative",
                validator=lambda d: (
                    d.get("review_count") is None or
                    int(d.get("review_count", 0)) >= 0
                ),
                severity="error",
            ),
        ]

    def clean_products(
        self,
        raw_data: list[dict[str, Any]],
        source: str = "amazon_bsr",
    ) -> tuple[list[dict[str, Any]], DataQualityReport]:
        """
        清洗产品数据列表。

        Args:
            raw_data: 原始产品数据列表
            source: 数据来源标识

        Returns:
            tuple: (cleaned_data, quality_report)
        """
        self.report = DataQualityReport()
        self.report.start()
        self.report.input_count = len(raw_data)

        cleaned = []
        batch_hashes: set[str] = set()

        for item in raw_data:
            try:
                processed = self._transform_item(item, source)

                item_hash = self._compute_hash(processed)

                if item_hash in self._seen_hashes or item_hash in batch_hashes:
                    self.report.dedup_count += 1
                    continue

                batch_hashes.add(item_hash)

                if not self._validate_rules(processed):
                    continue

                cleaned.append(processed)

            except Exception as e:
                self.report.errors.append({
                    "item": str(item)[:200],
                    "error": str(e),
                })
                logger.warning(f"ETL处理异常: {e}")

        self._update_hash(cleaned)
        self.report.output_count = len(cleaned)
        self.report.dropped_count = self.report.input_count - len(cleaned)
        self.report.finish()

        logger.info(
            f"📊 ETL完成: 输入={self.report.input_count} "
            f"输出={self.report.output_count} "
            f"去重={self.report.dedup_count} "
            f"丢弃={self.report.dropped_count} "
            f"通过率={self.report.pass_rate:.1%}"
        )

        return cleaned, self.report

    def _transform_item(self, item: dict[str, Any], source: str) -> dict[str, Any]:
        """单条数据转换。"""
        processed = dict(item)

        if "price" in processed and processed["price"] is not None:
            from src.crawlers.amazon import normalize_price
            processed["price_normalized"] = normalize_price(processed["price"])

        if "asin" in processed:
            processed["asin_upper"] = str(processed["asin"]).upper().strip()

        if "crawled_at" not in processed:
            processed["crawled_at"] = datetime.now(UTC).isoformat()

        processed["_source"] = source
        processed["_etl_processed_at"] = datetime.now(UTC).isoformat()

        return processed

    def _compute_hash(self, item: dict[str, Any]) -> str:
        """
        计算数据项的去重hash键(D12-T043 ASIN+日期唯一键)。
        """
        key_parts = [
            str(item.get("asin", "")),
            str(item.get("crawled_at", "")[:10]),
        ]
        return hashlib.md5("|".join(key_parts).encode()).hexdigest()

    def _is_duplicate(self, item: dict[str, Any]) -> bool:
        """
        去重检查(D12-T043 ASIN+日期唯一键)。

        基于ASIN+日期生成hash，已处理的跳过。
        """
        return self._compute_hash(item) in self._seen_hashes

    def _validate_rules(self, item: dict[str, Any]) -> bool:
        """执行所有数据质量规则。"""
        all_passed = True

        for rule in self.rules:
            passed = rule.validator(item)

            rule_key = rule.name
            if rule_key not in self.report.rule_results:
                self.report.rule_results[rule_key] = {
                    "passed": 0,
                    "failed": 0,
                }

            if passed:
                self.report.rule_results[rule_key]["passed"] += 1
            else:
                self.report.rule_results[rule_key]["failed"] += 1

                if rule.severity == "error":
                    all_passed = False
                elif rule.severity == "warning":
                    logger.debug(f"⚠️ 规则'{rule.name}'未通过")

        return all_passed

    def _update_hash(self, items: list[dict[str, Any]]):
        """更新已处理记录的hash集合。"""
        for item in items:
            key_parts = [
                str(item.get("asin", "")),
                str(item.get("crawled_at", "")[:10]),
            ]
            hash_key = hashlib.md5("|".join(key_parts).encode()).hexdigest()
            self._seen_hashes.add(hash_key)

    def reset(self):
        """重置Pipeline状态(用于新批次)。"""
        self._seen_hashes.clear()
        self.report = DataQualityReport()


def create_etl_pipeline() -> ETLPipeline:
    """创建ETL Pipeline实例。"""
    return ETLPipeline()
