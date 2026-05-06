from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.services.prompt_policy_service import PromptPolicyService

_ASCII_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+")
_COMPLAINT_KEYWORDS = ("退货", "投诉", "差评", "破损", "退款", "延迟")
_DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


@dataclass(frozen=True)
class TrainingExample:
    source_id: str
    label: int
    text: str
    source_type: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class TrainedAdapter:
    bias: float
    weights: dict[str, float]
    vocabulary: list[str]
    positive_examples: int
    negative_examples: int


class ModelFinetuneService:
    def __init__(
        self,
        session: Any,
        tenant_id: str,
        *,
        feedback_root: Path | None = None,
        scenario_root: Path | None = None,
        artifact_root: Path | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id or _DEFAULT_TENANT_ID
        self.policy_service = PromptPolicyService(session, tenant_id=self.tenant_id)
        self.workspace_root = Path(__file__).resolve().parents[2]
        self.feedback_root = Path(feedback_root) if feedback_root is not None else self.workspace_root / "artifacts" / "erp_local"
        self.scenario_root = Path(scenario_root) if scenario_root is not None else self.workspace_root / "artifacts" / "mock_scenarios"
        default_artifact_root = self.workspace_root / "artifacts" / "llm" / "model_finetune"
        self.artifact_root = Path(artifact_root) if artifact_root is not None else default_artifact_root

    async def run_weekly_finetune(self, *, registry_key: str = "default", train_days: int = 7) -> dict[str, Any]:
        registry = await self.policy_service.get_model_registry(registry_key) or {}
        previous_version = str(registry.get("active_model_version") or "qwen2.5-72b-v0")
        version_suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        new_version = f"{previous_version.split('-v')[0]}-v{version_suffix}"

        examples = self._collect_training_examples(train_days=train_days)
        if len({example.label for example in examples}) < 2:
            examples.extend(self._builtin_seed_examples())
        train_examples, validation_examples = self._split_examples(examples)
        adapter = self._train_adapter(train_examples)
        evaluation = self._evaluate_adapter(adapter, validation_examples, train_examples)
        training_snapshot = self._build_training_snapshot(train_days=train_days, examples=examples, train_examples=train_examples, validation_examples=validation_examples)
        artifact_payload = self._build_artifact_payload(
            registry_key=registry_key,
            previous_version=previous_version,
            new_version=new_version,
            adapter=adapter,
            examples=examples,
            train_examples=train_examples,
            validation_examples=validation_examples,
            training_snapshot=training_snapshot,
            evaluation=evaluation,
        )
        artifact_paths = self._write_artifacts(registry_key=registry_key, version=new_version, payload=artifact_payload)

        published = await self.policy_service.publish_model_registry(
            registry_key,
            {
                "active_model_version": new_version,
                "active_api_model_name": registry.get("active_api_model_name") or "Qwen/Qwen2.5-72B-Instruct",
                "training_backend": artifact_payload["training_backend"],
                "training_mode": artifact_payload["training_mode"],
                "latest_artifact_path": artifact_paths["latest_artifact_path"],
                "models": [
                    {
                        "model_version": new_version,
                        "base_model": previous_version,
                        "training_backend": artifact_payload["training_backend"],
                        "training_mode": artifact_payload["training_mode"],
                        "artifact_path": artifact_paths["versioned_artifact_path"],
                        "training_snapshot": training_snapshot,
                        "evaluation": evaluation,
                        "published_at": datetime.now(UTC).isoformat(),
                        "release_channel": "weekly-finetune",
                    },
                    *(registry.get("models") or []),
                ][:10],
                "description": f"weekly local finetune generated from {train_days}d feedback window",
            },
        )
        return {
            "registry_key": registry_key,
            "status": "completed",
            "training_mode": artifact_payload["training_mode"],
            "training_backend": artifact_payload["training_backend"],
            "previous_model_version": previous_version,
            "new_model_version": new_version,
            "training_snapshot": training_snapshot,
            "evaluation": evaluation,
            "artifact_path": artifact_paths["versioned_artifact_path"],
            "latest_artifact_path": artifact_paths["latest_artifact_path"],
            "model_registry": published,
        }

    def _collect_training_examples(self, *, train_days: int) -> list[TrainingExample]:
        examples: list[TrainingExample] = []
        examples.extend(self._load_feedback_examples(train_days=train_days))
        examples.extend(self._load_scenario_examples())
        return examples

    def _load_feedback_examples(self, *, train_days: int) -> list[TrainingExample]:
        feedback_payload = self._load_json(self.feedback_root / "crm" / "feedback.json")
        order_payload = self._load_json(self.feedback_root / "oms" / "orders.json")
        orders_by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for order in order_payload.get("items") or []:
            product_id = str(order.get("product_id") or order.get("task_id") or order.get("id") or order.get("order_id") or "")
            if product_id:
                orders_by_product[product_id].append(order)

        examples: list[TrainingExample] = []
        for item in feedback_payload.get("items") or []:
            product_id = str(item.get("product_id") or item.get("task_id") or item.get("id") or "")
            orders = orders_by_product.get(product_id, [])
            revenue = round(sum(float(order.get("revenue") or order.get("sales") or order.get("sales_7d") or 0.0) for order in orders), 4)
            units = sum(int(order.get("quantity") or order.get("units") or 0) for order in orders)
            rating = float(item.get("customer_score") or item.get("rating") or 0.0)
            review_count = int(item.get("review_count") or 0)
            feedback = str(item.get("feedback") or item.get("comment") or item.get("review_text") or "")
            complaint_hits = sum(keyword in feedback for keyword in _COMPLAINT_KEYWORDS)
            label = 1 if rating >= 4.2 and revenue > 0 and complaint_hits <= 1 else 0
            text = " ".join(
                [
                    str(item.get("product_name") or product_id),
                    feedback,
                    f"rating_{rating:.1f}",
                    f"review_count_{review_count}",
                    f"units_{units}",
                    f"revenue_{revenue:.1f}",
                    f"feedback_window_{train_days}d",
                ]
            ).strip()
            examples.append(
                TrainingExample(
                    source_id=str(item.get("id") or product_id or f"feedback-{len(examples) + 1}"),
                    label=label,
                    text=text,
                    source_type="erp_feedback",
                    metadata={
                        "product_id": product_id,
                        "rating": rating,
                        "review_count": review_count,
                        "units": units,
                        "revenue": revenue,
                        "complaint_hits": complaint_hits,
                    },
                )
            )
        return examples

    def _load_scenario_examples(self) -> list[TrainingExample]:
        examples: list[TrainingExample] = []
        for path in sorted(self.scenario_root.rglob("*.json")):
            label = self._scenario_label(path.stem)
            if label is None:
                continue
            payload = self._load_json(path)
            fragments = self._extract_text_fragments(payload)
            text = " ".join([path.stem.replace("_", " "), *fragments[:80]]).strip()
            examples.append(
                TrainingExample(
                    source_id=path.stem,
                    label=label,
                    text=text,
                    source_type="scenario_seed",
                    metadata={"path": path.as_posix()},
                )
            )
        return examples

    @staticmethod
    def _scenario_label(stem: str) -> int | None:
        positive = {
            "amazon_hot_selling",
            "google_trends_growth",
            "tiktok_trend_spike",
            "adoption_success",
            "listing_draft_created",
            "inventory_reserved",
        }
        negative = {
            "amazon_high_refund",
            "amazon_margin_pressure",
            "amazon_rate_limited",
            "google_trends_empty",
            "google_trends_spike_then_drop",
            "tiktok_auth_failed",
            "tiktok_high_heat_low_conversion",
            "ali1688_high_moq_long_leadtime",
            "ali1688_supplier_unstable",
            "profit_trace_decline",
            "supplier_timeout",
        }
        if stem in positive:
            return 1
        if stem in negative:
            return 0
        return None

    @staticmethod
    def _builtin_seed_examples() -> list[TrainingExample]:
        seeds = [
            ("builtin-positive-growth", 1, "销量增长 rating_4.8 reviews_120 revenue_5600 trend_growth hot_selling"),
            ("builtin-positive-profit", 1, "利润稳定 毛利提升 inventory_ready conversion_up satisfied_customer"),
            ("builtin-negative-refund", 0, "高退款 差评 增长放缓 margin_pressure return_risk supplier_unstable"),
            ("builtin-negative-delay", 0, "长交期 交付延迟 低转化 投诉增多 stockout_risk"),
        ]
        return [
            TrainingExample(source_id=source_id, label=label, text=text, source_type="builtin_seed", metadata={})
            for source_id, label, text in seeds
        ]

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _extract_text_fragments(self, payload: Any) -> list[str]:
        fragments: list[str] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                fragments.append(str(key))
                fragments.extend(self._extract_text_fragments(value))
            return fragments
        if isinstance(payload, list):
            for item in payload:
                fragments.extend(self._extract_text_fragments(item))
            return fragments
        if payload is None:
            return fragments
        if isinstance(payload, bool):
            fragments.append("true" if payload else "false")
            return fragments
        fragments.append(str(payload))
        return fragments

    @staticmethod
    def _split_examples(examples: list[TrainingExample]) -> tuple[list[TrainingExample], list[TrainingExample]]:
        grouped: dict[int, list[TrainingExample]] = defaultdict(list)
        for example in sorted(examples, key=lambda item: item.source_id):
            grouped[example.label].append(example)

        train_examples: list[TrainingExample] = []
        validation_examples: list[TrainingExample] = []
        for label_examples in grouped.values():
            validation_count = 1 if len(label_examples) >= 3 else 0
            validation_examples.extend(label_examples[:validation_count])
            train_examples.extend(label_examples[validation_count:])

        if not validation_examples:
            validation_examples = list(train_examples)
        if not train_examples:
            train_examples = list(validation_examples)
        return train_examples, validation_examples

    def _train_adapter(self, examples: list[TrainingExample]) -> TrainedAdapter:
        token_frequency = Counter()
        positive_counts = Counter()
        negative_counts = Counter()
        positive_examples = sum(1 for example in examples if example.label == 1)
        negative_examples = max(len(examples) - positive_examples, 1)

        for example in examples:
            counts = Counter(self._tokenize(example.text))
            token_frequency.update(counts.keys())
            if example.label == 1:
                positive_counts.update(counts)
            else:
                negative_counts.update(counts)

        vocabulary = [token for token, _ in token_frequency.most_common(256)]
        if not vocabulary:
            vocabulary = ["fallback_signal"]
        alpha = 1.0
        positive_total = alpha * len(vocabulary) + sum(positive_counts[token] for token in vocabulary)
        negative_total = alpha * len(vocabulary) + sum(negative_counts[token] for token in vocabulary)
        weights = {
            token: math.log((positive_counts[token] + alpha) / positive_total)
            - math.log((negative_counts[token] + alpha) / negative_total)
            for token in vocabulary
        }
        bias = math.log((positive_examples + alpha) / (positive_examples + negative_examples + 2 * alpha)) - math.log(
            (negative_examples + alpha) / (positive_examples + negative_examples + 2 * alpha)
        )
        return TrainedAdapter(
            bias=bias,
            weights=weights,
            vocabulary=vocabulary,
            positive_examples=positive_examples,
            negative_examples=negative_examples,
        )

    def _evaluate_adapter(
        self,
        adapter: TrainedAdapter,
        validation_examples: list[TrainingExample],
        train_examples: list[TrainingExample],
    ) -> dict[str, Any]:
        majority_label = 1 if adapter.positive_examples >= adapter.negative_examples else 0
        correct = 0
        baseline_correct = 0
        predictions: list[dict[str, Any]] = []
        tp = fp = tn = fn = 0

        for example in validation_examples:
            probability = self._predict_probability(adapter, example.text)
            predicted_label = 1 if probability >= 0.5 else 0
            correct += int(predicted_label == example.label)
            baseline_correct += int(majority_label == example.label)
            if predicted_label == 1 and example.label == 1:
                tp += 1
            elif predicted_label == 1 and example.label == 0:
                fp += 1
            elif predicted_label == 0 and example.label == 0:
                tn += 1
            else:
                fn += 1
            predictions.append(
                {
                    "source_id": example.source_id,
                    "source_type": example.source_type,
                    "actual_label": example.label,
                    "predicted_label": predicted_label,
                    "probability": round(probability, 6),
                }
            )

        total = max(len(validation_examples), 1)
        validation_score = round(correct / total, 6)
        baseline_score = round(baseline_correct / total, 6)
        improvement = round(validation_score - baseline_score, 6)
        top_positive = [
            {"token": token, "weight": round(weight, 6)}
            for token, weight in sorted(adapter.weights.items(), key=lambda item: item[1], reverse=True)[:8]
        ]
        top_negative = [
            {"token": token, "weight": round(weight, 6)}
            for token, weight in sorted(adapter.weights.items(), key=lambda item: item[1])[:8]
        ]
        return {
            "validation_score": validation_score,
            "baseline_score": baseline_score,
            "improvement": improvement,
            "not_regressed": validation_score >= baseline_score,
            "validation_examples": len(validation_examples),
            "train_examples": len(train_examples),
            "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
            "predictions": predictions,
            "top_positive_features": top_positive,
            "top_negative_features": top_negative,
        }

    def _build_training_snapshot(
        self,
        *,
        train_days: int,
        examples: list[TrainingExample],
        train_examples: list[TrainingExample],
        validation_examples: list[TrainingExample],
    ) -> dict[str, Any]:
        source_breakdown = Counter(example.source_type for example in examples)
        positive_examples = sum(1 for example in examples if example.label == 1)
        negative_examples = sum(1 for example in examples if example.label == 0)
        return {
            "train_window_days": train_days,
            "sample_count": len(examples),
            "positive_feedback_cases": positive_examples,
            "negative_feedback_cases": negative_examples,
            "human_labeled_cases": source_breakdown.get("erp_feedback", 0),
            "train_example_count": len(train_examples),
            "validation_example_count": len(validation_examples),
            "source_breakdown": dict(source_breakdown),
        }

    def _build_artifact_payload(
        self,
        *,
        registry_key: str,
        previous_version: str,
        new_version: str,
        adapter: TrainedAdapter,
        examples: list[TrainingExample],
        train_examples: list[TrainingExample],
        validation_examples: list[TrainingExample],
        training_snapshot: dict[str, Any],
        evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "registry_key": registry_key,
            "training_mode": "local-real",
            "training_backend": "cpu-feedback-adapter",
            "base_model_version": previous_version,
            "new_model_version": new_version,
            "dataset_summary": training_snapshot,
            "adapter_summary": {
                "bias": round(adapter.bias, 6),
                "vocabulary_size": len(adapter.vocabulary),
                "positive_examples": adapter.positive_examples,
                "negative_examples": adapter.negative_examples,
            },
            "evaluation": evaluation,
            "train_sources": [
                {"source_id": example.source_id, "label": example.label, "source_type": example.source_type}
                for example in train_examples
            ],
            "validation_sources": [
                {"source_id": example.source_id, "label": example.label, "source_type": example.source_type}
                for example in validation_examples
            ],
            "example_count": len(examples),
        }

    def _write_artifacts(self, *, registry_key: str, version: str, payload: dict[str, Any]) -> dict[str, str]:
        target_dir = self.artifact_root / registry_key
        target_dir.mkdir(parents=True, exist_ok=True)
        latest_path = target_dir / "latest.json"
        versioned_path = target_dir / f"{version}.json"
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        latest_path.write_text(serialized, encoding="utf-8")
        versioned_path.write_text(serialized, encoding="utf-8")
        return {
            "latest_artifact_path": latest_path.as_posix(),
            "versioned_artifact_path": versioned_path.as_posix(),
        }

    def _predict_probability(self, adapter: TrainedAdapter, text: str) -> float:
        score = adapter.bias
        counts = Counter(self._tokenize(text))
        for token, count in counts.items():
            score += adapter.weights.get(token, 0.0) * count
        clipped = max(min(score, 40.0), -40.0)
        return 1.0 / (1.0 + math.exp(-clipped))

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        lowered = text.lower()
        tokens = [token for token in _ASCII_TOKEN_RE.findall(lowered) if len(token) > 1 and not token.isdigit()]
        for block in _CJK_TOKEN_RE.findall(lowered):
            if len(block) <= 2:
                tokens.append(block)
            tokens.extend(block[index : index + 2] for index in range(len(block) - 1))
        compact = re.sub(r"\s+", "", lowered)
        if not tokens and compact:
            tokens.extend(compact[index : index + 2] for index in range(max(len(compact) - 1, 0)))
        return tokens or ["empty"]
