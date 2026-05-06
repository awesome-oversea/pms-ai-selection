from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib import robotparser
from urllib.parse import urlparse


@dataclass
class CrawlGovernanceResult:
    url: str
    allowed: bool
    host: str
    user_agent: str
    robots_url: str
    privacy_redacted: bool
    redacted_fields: list[str]
    recommended_delay_seconds: float
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "allowed": self.allowed,
            "host": self.host,
            "user_agent": self.user_agent,
            "robots_url": self.robots_url,
            "privacy_redacted": self.privacy_redacted,
            "redacted_fields": self.redacted_fields,
            "recommended_delay_seconds": self.recommended_delay_seconds,
            "reason": self.reason,
        }


class CrawlGovernanceService:
    DEFAULT_USER_AGENT = "PMS-SelectionBot/1.0"

    @staticmethod
    def _redact_privacy_fields(record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        payload = dict(record)
        redacted: list[str] = []
        for key in list(payload.keys()):
            lowered = key.lower()
            if any(token in lowered for token in ("email", "phone", "mobile", "address", "identity", "id_card", "name")):
                payload[key] = "[redacted]"
                redacted.append(key)
        return payload, redacted

    def evaluate_url(self, *, url: str, user_agent: str | None = None, sample_record: dict[str, Any] | None = None) -> dict[str, Any]:
        parsed = urlparse(url)
        host = parsed.netloc
        robots_url = f"{parsed.scheme or 'https'}://{host}/robots.txt" if host else ""
        user_agent_value = user_agent or self.DEFAULT_USER_AGENT

        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        allowed = True
        reason = None
        try:
            rp.read()
            allowed = rp.can_fetch(user_agent_value, url)
            if not allowed:
                reason = "robots.txt disallow"
        except Exception:
            allowed = True
            reason = "robots unavailable, fallback allow"

        _, redacted_fields = self._redact_privacy_fields(sample_record or {})
        result = CrawlGovernanceResult(
            url=url,
            allowed=allowed,
            host=host,
            user_agent=user_agent_value,
            robots_url=robots_url,
            privacy_redacted=bool(redacted_fields),
            redacted_fields=redacted_fields,
            recommended_delay_seconds=1.5,
            reason=reason,
        )
        return result.to_dict()


class BloomFilterDeduper:
    def __init__(self, size: int = 2048):
        self.size = size
        self._bits = bytearray(size)

    def _indexes(self, value: str) -> tuple[int, int]:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % self.size, int(digest[8:16], 16) % self.size

    def add(self, value: str) -> None:
        for idx in self._indexes(value):
            self._bits[idx] = 1

    def contains(self, value: str) -> bool:
        return all(self._bits[idx] == 1 for idx in self._indexes(value))


class CrawlDataQualityService:
    REQUIRED_BY_SOURCE: dict[str, tuple[str, ...]] = {
        "rss": ("title",),
        "amazon": ("asin", "name", "url"),
        "review": ("review_id", "asin", "rating"),
    }

    def __init__(self) -> None:
        self.deduper = BloomFilterDeduper()

    def validate_records(self, *, source: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        required = self.REQUIRED_BY_SOURCE.get(source, tuple())
        accepted: list[dict[str, Any]] = []
        duplicates = 0
        invalid = 0
        anomaly_count = 0

        for record in records:
            fingerprint = str(record.get("url") or record.get("review_id") or record.get("asin") or record.get("title") or record)
            if self.deduper.contains(fingerprint):
                duplicates += 1
                continue
            self.deduper.add(fingerprint)

            if any(not record.get(field) for field in required):
                invalid += 1
                continue

            rating = record.get("rating")
            if rating is not None:
                try:
                    rating_value = float(rating)
                    if rating_value < 0 or rating_value > 5:
                        anomaly_count += 1
                except Exception:
                    anomaly_count += 1

            accepted.append(record)

        total = len(records)
        valid = len(accepted)
        return {
            "source": source,
            "total_records": total,
            "valid_records": valid,
            "duplicate_count": duplicates,
            "invalid_count": invalid,
            "anomaly_count": anomaly_count,
            "validity_rate": valid / max(total, 1),
            "is_acceptable": valid / max(total, 1) >= 0.8 and anomaly_count <= max(1, total * 0.1),
            "accepted_records": accepted,
        }
