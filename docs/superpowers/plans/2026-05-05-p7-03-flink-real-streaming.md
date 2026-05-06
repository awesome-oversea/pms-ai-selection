# P7-03 Flink实时流处理（真实部署） Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐本地真实 Flink + Kafka 实时消费与 checkpoint 恢复验收链路，使 P7-03 达到任务清单和验收标准要求的“真实 Kafka 消费与 checkpoint 验证完成”。

**Architecture:** 以现有 `LocalFlinkCheckpointAcceptanceService` 为主执行器，复用 WSL Docker 中的 Flink JobManager / TaskManager 与 Kafka broker，提交真实 Java Flink job，向真实 Kafka topic 写入业务事件，验证 checkpoint、故障恢复、最终业务投影，并把结果同步到 `artifacts/data_platform/flink_checkpoint_acceptance_latest.json` 供状态接口和验收使用。保持现有 demo SQL manifest 能力不变，只补“真实流式消费 + checkpoint”这条正式验收链路。

**Tech Stack:** Python 3.11, FastAPI, aiokafka, Docker/WSL, Apache Flink 2.2.0, Java 17, pytest

---

## File Structure

### Existing files to modify
- `src/services/local_flink_checkpoint_acceptance_service.py` — 真实 Flink checkpoint 验收主服务；负责环境探测、topic 建立、提交 job、checkpoint/恢复/投影校验、工件落盘。
- `src/services/data_platform_runtime_service.py` — 聚合 Flink checkpoint 最新验收工件，暴露到数据平台状态摘要。
- `src/api/v1/endpoints/system.py` — 暴露 `/api/v1/data-platform/runtime`、`/api/v1/data-platform/status` 等接口时带出最新 checkpoint 验收状态。
- `tests/test_local_flink_checkpoint_acceptance.py` — 覆盖 checkpoint 验收服务的纯逻辑单元测试。
- `tests/test_data_platform_runtime_service.py` — 覆盖运行态聚合结果是否包含 checkpoint 验收工件。
- `tests/test_api_integration.py` — 覆盖 API 层对 runtime / status 的输出契约。

### Existing files to verify but likely not modify
- `scripts/run_local_flink_checkpoint_acceptance.py` — 手动/CI 执行真实 Flink checkpoint 验收脚本入口。
- `jobs/local_flink_checkpoint_acceptance/src/main/java/com/pms/acceptance/flink/LocalKafkaCheckpointAcceptanceJob.java` — 真实 Flink Java job；负责 Kafka source、checkpoint、fail-once 恢复、业务投影输出。
- `tests/test_local_platform_compose.py` — 确认 compose 中包含 flink-jobmanager / flink-taskmanager。
- `artifacts/ops/local_flink_demo_job_acceptance.json` — 现有 demo SQL 作业工件，作为 P7-03 已完成前半段证据保留。

### New files to create
- `tests/test_local_flink_checkpoint_acceptance_service_run.py` — 用 stub/mocks 覆盖 `run()` 的成功摘要结构和关键检查项。
- `artifacts/data_platform/flink_checkpoint_acceptance_latest.json` — 最新 checkpoint 验收摘要工件（由代码生成，不手写）。

---

### Task 1: 固化 P7-03 验收口径到测试

**Files:**
- Modify: `tests/test_local_flink_checkpoint_acceptance.py`
- Create: `tests/test_local_flink_checkpoint_acceptance_service_run.py`
- Reference: `任务清单.md:197`
- Reference: `验收标准.md:217`

- [ ] **Step 1: 为运行摘要新增失败前恢复与 checkpoint 检查的单元测试**

```python
from __future__ import annotations

from pathlib import Path

from src.services.local_flink_checkpoint_acceptance_service import LocalFlinkCheckpointAcceptanceService


def test_projection_check_fails_when_projection_missing():
    expected = LocalFlinkCheckpointAcceptanceService.expected_projection("selection-task-flink-checkpoint-us-001")

    check = LocalFlinkCheckpointAcceptanceService.projection_check(expected, None)

    assert check["passed"] is False
    assert check["detail"] == "projection missing"


def test_parse_consumer_group_ignores_headers_and_errors():
    raw = """
GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG
Error: group not found
pms-group test-topic 0 5 5 0
"""

    rows = LocalFlinkCheckpointAcceptanceService.parse_consumer_group(raw)

    assert rows == [
        {
            "group": "pms-group",
            "topic": "test-topic",
            "partition": 0,
            "current_offset": 5,
            "log_end_offset": 5,
            "lag": 0,
        }
    ]
```

- [ ] **Step 2: 新增 `run()` 成功摘要结构测试，先写失败测试**

```python
from __future__ import annotations

import json
from pathlib import Path

from src.services.local_flink_checkpoint_acceptance_service import LocalFlinkCheckpointAcceptanceService


class _StubService(LocalFlinkCheckpointAcceptanceService):
    def _inspect_environment(self):
        return {
            "containers": {
                self.JOBMANAGER_CONTAINER: {"running": True, "status": "running"},
                self.TASKMANAGER_CONTAINER: {"running": True, "status": "running"},
                self.KAFKA_CONTAINER: {"running": True, "status": "running"},
            },
            "kafka_connectors": [],
            "ready": True,
            "stream_runtime_ready": True,
        }

    def _build_job(self, run_dir: Path):
        jar_path = run_dir / "job.jar"
        jar_path.write_bytes(b"jar")
        payload = {"jar_path": str(jar_path)}
        self._write_json(run_dir / "job_build_manifest.json", payload)
        return payload

    def _ensure_topic(self, topic: str) -> None:
        return None

    def _submit_job(self, *, job_jar: Path, topic: str, group_id: str, run_dir_name: str):
        return {
            "job_id": "job-001",
            "output_dir": "/tmp/output",
            "submit_output": "submitted",
        }

    def _wait_for_running(self, job_id: str, *, timeout_seconds: float = 90.0):
        return {"state": "RUNNING", "history": [{"state": "RUNNING"}], "payload": {"state": "RUNNING"}}

    def _produce_events(self, topic: str, events, artifact_path: Path) -> None:
        artifact_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in events), encoding="utf-8")

    def _wait_for_checkpoint(self, job_id: str, *, timeout_seconds: float = 120.0):
        return {
            "completed": 1,
            "payload": {"counts": {"completed": 1}, "latest": {"completed": {"id": 1}}},
            "history": [{"completed": 1}],
        }

    def _describe_consumer_group(self, group_id: str):
        return {"raw": "", "rows": [{"group": group_id, "topic": "topic-001", "lag": 0}]}

    def _wait_for_recovery(self, job_id: str, *, timeout_seconds: float = 120.0):
        return {
            "recovered": True,
            "history": [
                {"state": "RUNNING"},
                {"state": "FAILING"},
                {"state": "RUNNING"},
            ],
            "payload": {"state": "RUNNING"},
        }

    def _wait_for_projection(self, *, output_dir: str, product_id: str, expected_event_count: int, timeout_seconds: float = 120.0):
        latest = self.expected_projection(product_id)
        latest["updated_at"] = "2026-05-05T00:00:00+00:00"
        return {"rows": [latest], "latest": latest}

    def _checkpoint_payload(self, job_id: str):
        return {"counts": {"completed": 1}, "latest": {"completed": {"id": 1}}}

    def _exceptions_payload(self, job_id: str):
        return {"all-exceptions": [{"exception": "intentional checkpoint recovery trigger"}]}

    def _cancel_job(self, job_id: str) -> str:
        return "cancelled"


def test_run_writes_latest_data_platform_artifact(tmp_path: Path):
    service = _StubService(root=tmp_path)

    summary = service.run(output_root=tmp_path / "artifacts" / "local_flink_checkpoint")

    latest_path = tmp_path / "artifacts" / "data_platform" / "flink_checkpoint_acceptance_latest.json"
    assert summary["accepted"] is True
    assert latest_path.exists()
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["job_id"] == "job-001"
    assert any(item["name"] == "flink_job_has_completed_checkpoint" for item in latest["checks"])
    assert any(item["name"] == "flink_job_recovers_after_controlled_failure" for item in latest["checks"])
```

- [ ] **Step 3: 运行新增测试，确认先失败**

Run: `rtk pytest tests/test_local_flink_checkpoint_acceptance.py tests/test_local_flink_checkpoint_acceptance_service_run.py -q`
Expected: 新增 `test_run_writes_latest_data_platform_artifact` 先因缺失或不完整摘要结构失败。

- [ ] **Step 4: 最小实现缺失的摘要字段或工件同步逻辑**

```python
summary = {
    "status": self._status_from_checks(checks),
    "accepted": all(bool(item.get("passed")) for item in checks),
    "generated_at": self._now_iso(),
    "run_id": run_dir.name,
    "run_dir": str(run_dir),
    "job_id": job_id,
    "input_topic": topic,
    "consumer_group": group_id,
    "checkpoint_summary": {
        "completed": checkpoint_completed,
        "latest_completed": latest_completed,
    },
    "recovery_summary": {
        "recovered": bool(recovery_result.get("recovered")),
        "restart_states": sorted(restart_states),
    },
    "checks": checks,
    "artifacts": {
        **partial_artifacts,
        "summary": str(summary_path),
    },
}
self._write_json(summary_path, summary)
self.data_platform_root.mkdir(parents=True, exist_ok=True)
self._write_json(self.data_platform_root / "flink_checkpoint_acceptance_latest.json", summary)
```

- [ ] **Step 5: 重新运行测试确认通过**

Run: `rtk pytest tests/test_local_flink_checkpoint_acceptance.py tests/test_local_flink_checkpoint_acceptance_service_run.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
rtk git add tests/test_local_flink_checkpoint_acceptance.py tests/test_local_flink_checkpoint_acceptance_service_run.py src/services/local_flink_checkpoint_acceptance_service.py
rtk git commit -m "test: lock flink checkpoint acceptance summary"
```

### Task 2: 让数据平台运行态稳定暴露 checkpoint 验收结果

**Files:**
- Modify: `src/services/data_platform_runtime_service.py`
- Modify: `tests/test_data_platform_runtime_service.py`
- Reference: `src/api/v1/endpoints/system.py:726`

- [ ] **Step 1: 先写聚合层失败测试，明确 `stream_engine` 必须带出 checkpoint 验收摘要**

```python
def test_data_platform_runtime_service_reads_flink_checkpoint_acceptance_artifact(tmp_path: Path):
    artifact_root = tmp_path / "artifacts" / "data_platform"
    artifact_root.mkdir(parents=True, exist_ok=True)

    payloads = {
        "scheduler_manifest.json": {"scheduler": "airflow-prefect-compatible"},
        "kettle_etl_manifest.json": {"etl_engine": "kettle-compatible", "supported_runners": [{"runner": "python-local"}]},
        "kettle_etl_job_latest.json": {
            "job_type": "kettle_etl",
            "etl_engine": "pandas-dask-compatible",
            "runner": "python-local",
            "quality_summary": {"all_required_fields_ready": True, "quality_score": 0.91, "business_consumable": True, "failure_summary": []},
            "latest_run_quality_score": 0.91,
            "business_consumable": True,
            "failure_summary": [],
        },
        "flink_feature_job_manifest.json": {"job_type": "flink_feature_processing"},
        "flink_trendwide_manifest.json": {"job_type": "flink_trend_wide_table"},
        "flink_forum_topic_manifest.json": {"job_type": "flink_forum_topic_modeling"},
        "flink_checkpoint_acceptance_latest.json": {
            "accepted": True,
            "job_id": "job-flink-checkpoint-001",
            "input_topic": "pms-flink-checkpoint-test",
            "checkpoint_summary": {"completed": 1},
        },
        "batch_job_latest.json": {"status": "completed", "engine": "spark-compatible"},
        "stream_job_latest.json": {"status": "completed", "engine": "flink-compatible"},
        "spark_backfill_job_latest.json": {"job_type": "spark_historical_backfill"},
    }
```

- [ ] **Step 2: 运行测试确认当前行为是否缺字段或契约不稳**

Run: `rtk pytest tests/test_data_platform_runtime_service.py -q`
Expected: 若 `checkpoint_acceptance` 未稳定进入 `flink` / `jobs` / `processing_engines.stream_engine`，测试失败。

- [ ] **Step 3: 最小实现聚合逻辑**

```python
flink_checkpoint_acceptance = self._read_json("flink_checkpoint_acceptance_latest.json") or {}

return {
    "flink": {
        "feature_processing": flink_feature,
        "trend_wide_table": flink_trendwide,
        "forum_topic_modeling": flink_forum,
        "checkpoint_acceptance": flink_checkpoint_acceptance,
    },
    "jobs": {
        "kettle_etl": kettle_job,
        "batch": batch,
        "stream": stream,
        "spark_backfill": spark_backfill,
        "flink_checkpoint_acceptance": flink_checkpoint_acceptance,
    },
    "processing_engines": {
        "stream_engine": {
            "mode": stream.get("engine"),
            "latest_run": stream,
            "checkpoint_acceptance": flink_checkpoint_acceptance,
        },
    },
}
```

- [ ] **Step 4: 重新运行测试确认通过**

Run: `rtk pytest tests/test_data_platform_runtime_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
rtk git add src/services/data_platform_runtime_service.py tests/test_data_platform_runtime_service.py
rtk git commit -m "feat: expose flink checkpoint acceptance in runtime status"
```

### Task 3: 固化 API 契约，确保运行态接口能复核 P7-03

**Files:**
- Modify: `tests/test_api_integration.py`
- Verify: `src/api/v1/endpoints/system.py`

- [ ] **Step 1: 先写 API 集成测试，要求 `/api/v1/data-platform/runtime` 与 `/api/v1/data-platform/status` 都能带出 checkpoint 验收结果**

```python
def test_data_platform_runtime_exposes_flink_checkpoint_acceptance(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "src.api.v1.endpoints.system.DataPlatformRuntimeService.build_status",
        lambda self: {
            "scheduler": {"scheduler": "airflow-prefect-compatible"},
            "kettle": {"etl_engine": "kettle-compatible", "latest_run": {}},
            "flink": {
                "feature_processing": {"job_type": "flink_feature_processing"},
                "trend_wide_table": {"job_type": "flink_trend_wide_table"},
                "forum_topic_modeling": {"job_type": "flink_forum_topic_modeling"},
                "checkpoint_acceptance": {
                    "accepted": True,
                    "job_id": "job-001",
                    "checkpoint_summary": {"completed": 1},
                },
            },
            "jobs": {
                "stream": {"status": "completed", "engine": "flink-compatible"},
                "flink_checkpoint_acceptance": {"accepted": True, "job_id": "job-001"},
            },
            "processing_engines": {
                "etl_engine": {"mode": "pandas-dask-compatible"},
                "stream_engine": {
                    "mode": "flink-compatible",
                    "latest_run": {"status": "completed"},
                    "checkpoint_acceptance": {"accepted": True, "job_id": "job-001"},
                },
            },
            "ray_embedding": {"target_qps": 5000},
            "platform_ready": True,
        },
    )

    runtime_resp = client.get("/api/v1/data-platform/runtime", headers=auth_headers)
    assert runtime_resp.status_code == 200
    runtime_payload = runtime_resp.json()
    assert runtime_payload["processing_engines"]["stream_engine"]["checkpoint_acceptance"]["accepted"] is True
    assert runtime_payload["jobs"]["flink_checkpoint_acceptance"]["job_id"] == "job-001"
```

- [ ] **Step 2: 运行 API 测试确认先失败或确认契约现状**

Run: `rtk pytest tests/test_api_integration.py -q -k "data_platform_runtime_exposes_flink_checkpoint_acceptance or data_platform_status_routes"`
Expected: 若路由层未透传 `checkpoint_acceptance`，测试失败；否则记录通过并保留测试。

- [ ] **Step 3: 如有必要，最小调整接口透传实现**

```python
@router.get("/data-platform/runtime")
async def data_platform_runtime_status(...):
    return DataPlatformRuntimeService().build_status()
```

```python
@router.get("/data-platform/status")
async def data_platform_status(...):
    runtime = DataPlatformRuntimeService().build_status()
    return {
        **runtime,
        "platform_ready": runtime.get("platform_ready", False),
    }
```

- [ ] **Step 4: 重新运行 API 测试确认通过**

Run: `rtk pytest tests/test_api_integration.py -q -k "data_platform_runtime_exposes_flink_checkpoint_acceptance or data_platform_status_routes"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_api_integration.py src/api/v1/endpoints/system.py
rtk git commit -m "test: cover flink checkpoint runtime api contract"
```

### Task 4: 执行真实本地 Flink checkpoint 验收并落盘证据

**Files:**
- Verify: `scripts/run_local_flink_checkpoint_acceptance.py`
- Verify: `jobs/local_flink_checkpoint_acceptance/src/main/java/com/pms/acceptance/flink/LocalKafkaCheckpointAcceptanceJob.java`
- Output: `artifacts/local_flink_checkpoint/<run_id>/summary.json`
- Output: `artifacts/data_platform/flink_checkpoint_acceptance_latest.json`

- [ ] **Step 1: 先运行 compose 相关测试，确认本地平台编排仍包含 Flink 依赖**

Run: `rtk pytest tests/test_local_platform_compose.py tests/test_flink_manifests_scripts.py tests/test_data_lake_flink_manifests.py -q`
Expected: PASS

- [ ] **Step 2: 运行 checkpoint 验收脚本，先观察真实失败点**

Run: `rtk python scripts/run_local_flink_checkpoint_acceptance.py`
Expected: 若本地环境未就绪，返回非 0，并在输出中明确是容器、Kafka 网络、checkpoint 还是 job 恢复问题。

- [ ] **Step 3: 根据失败点做最小实现修复**

```python
if not environment.get("ready"):
    raise RuntimeError("local flink/kafka environment is not ready")
if not environment.get("stream_runtime_ready"):
    raise RuntimeError(
        "jobmanager cannot reach kafka bootstrap pms-local-kafka:29092; "
        "ensure Kafka joins the fms_default network before running acceptance"
    )
```

```java
env.enableCheckpointing(2_000L);
env.getCheckpointConfig().setMinPauseBetweenCheckpoints(1_000L);
env.getCheckpointConfig().setCheckpointTimeout(60_000L);
env.getCheckpointConfig().setMaxConcurrentCheckpoints(1);
```

```java
if ("control.fail_once".equals(eventType)) {
  File marker = new File(failMarkerPath);
  if (!marker.exists()) {
    Files.writeString(marker.toPath(), "triggered", StandardCharsets.UTF_8);
    throw new RuntimeException("intentional checkpoint recovery trigger");
  }
  return;
}
```

- [ ] **Step 4: 重新执行真实验收直到通过**

Run: `rtk python scripts/run_local_flink_checkpoint_acceptance.py`
Expected: 输出 JSON 且 `accepted=true`，同时生成：
- `artifacts/local_flink_checkpoint/<run_id>/summary.json`
- `artifacts/data_platform/flink_checkpoint_acceptance_latest.json`

- [ ] **Step 5: 校验关键工件字段**

Run: `rtk python -c "import json, pathlib; p=pathlib.Path('artifacts/data_platform/flink_checkpoint_acceptance_latest.json'); d=json.loads(p.read_text(encoding='utf-8')); print(json.dumps({'accepted': d['accepted'], 'job_id': d['job_id'], 'completed': d['checkpoint_summary']['completed'], 'recovered': d['recovery_summary']['recovered']}, ensure_ascii=False, indent=2))"`
Expected:

```json
{
  "accepted": true,
  "job_id": "<non-empty>",
  "completed": 1,
  "recovered": true
}
```

- [ ] **Step 6: Commit**

```bash
rtk git add scripts/run_local_flink_checkpoint_acceptance.py jobs/local_flink_checkpoint_acceptance/src/main/java/com/pms/acceptance/flink/LocalKafkaCheckpointAcceptanceJob.java src/services/local_flink_checkpoint_acceptance_service.py artifacts/data_platform/flink_checkpoint_acceptance_latest.json
rtk git commit -m "feat: complete local flink checkpoint acceptance"
```

### Task 5: 回归 P7-03 相关接口与状态面

**Files:**
- Modify: `tests/test_api_integration.py`
- Verify: `src/services/data_platform_runtime_service.py`
- Verify: `src/api/v1/endpoints/system.py`

- [ ] **Step 1: 运行 P7-03 相关回归测试集合**

Run: `rtk pytest tests/test_local_flink_checkpoint_acceptance.py tests/test_local_flink_checkpoint_acceptance_service_run.py tests/test_data_platform_runtime_service.py tests/test_api_integration.py tests/test_local_platform_compose.py tests/test_flink_manifests_scripts.py tests/test_data_lake_flink_manifests.py -q`
Expected: PASS

- [ ] **Step 2: 运行数据平台接口最小冒烟，确认可复核**

Run: `rtk python -m pytest tests/test_api_integration.py -q -k "data_platform_runtime or external_collection_readiness_route_exists"`
Expected: PASS

- [ ] **Step 3: 检查是否满足任务清单与验收标准**

```text
通过条件：
1. WSL Flink JobManager/TaskManager 已实机拉起（保留现有 demo 证据）
2. Kafka 实时消费链路已通过真实 topic 写入与消费组校验
3. 至少 1 次 completed checkpoint 已被 summary 记录
4. 控制性失败后 job 已恢复并继续输出业务投影
5. 最新工件已进入 data-platform runtime/status 接口可复核
```

- [ ] **Step 4: Commit**

```bash
rtk git add tests/test_local_flink_checkpoint_acceptance.py tests/test_local_flink_checkpoint_acceptance_service_run.py tests/test_data_platform_runtime_service.py tests/test_api_integration.py
rtk git commit -m "test: verify p7-03 flink runtime acceptance"
```

---

## Self-Review

- Spec coverage checked against `任务清单.md:197` and `验收标准.md:217`: 本计划覆盖了真实 Kafka 消费、checkpoint、故障恢复、运行态证据和接口可复核；未包含 K8s 化，因为当前任务清单把 K8s 化列为后续继续验收内容，不是本轮必须完成的最小闭环。
- Placeholder scan completed: 无 `TBD` / `TODO` / “后续补充” 类占位步骤。
- Type consistency checked: `checkpoint_acceptance`, `flink_checkpoint_acceptance_latest.json`, `processing_engines.stream_engine.checkpoint_acceptance`, `job_id`, `accepted`, `checkpoint_summary`, `recovery_summary` 在所有任务中保持一致。
