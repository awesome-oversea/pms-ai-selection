from __future__ import annotations

import pytest
from src.services.report_center_service import ReportCenterService


@pytest.mark.asyncio
async def test_report_center_service_generate_and_download_pdf_csv_xlsx_ppt_and_share():
    service = ReportCenterService()

    pdf_report = await service.generate(report_type="daily", format="pdf", task_id="task-1", params={"task_count": 5})
    assert pdf_report["download_format"] == "pdf"
    pdf_download = await service.build_download(pdf_report["report_id"])
    assert pdf_download is not None
    pdf_content, pdf_type, pdf_name = pdf_download
    assert pdf_type == "application/pdf"
    assert pdf_name.endswith(".pdf")
    assert pdf_content.startswith(b"%PDF")

    excel_report = await service.generate(report_type="monthly", format="excel", task_id="task-2", params={"roi": 2.5})
    csv_download = await service.build_download(excel_report["report_id"])
    assert csv_download is not None
    csv_content, csv_type, csv_name = csv_download
    assert csv_type.startswith("text/csv")
    assert csv_name.endswith(".csv")
    assert b"title" in csv_content

    xlsx_report = await service.generate(report_type="weekly", format="xlsx", task_id="task-3", params={"opportunities": 3})
    xlsx_download = await service.build_download(xlsx_report["report_id"])
    assert xlsx_download is not None
    xlsx_content, xlsx_type, xlsx_name = xlsx_download
    assert xlsx_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert xlsx_name.endswith(".xlsx")
    assert xlsx_content.startswith(b"PK")

    ppt_report = await service.generate(report_type="weekly", format="ppt", task_id="task-4", params={"trend_change": 0.1})
    ppt_download = await service.build_download(ppt_report["report_id"])
    assert ppt_download is not None
    ppt_content, ppt_type, ppt_name = ppt_download
    assert ppt_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    assert ppt_name.endswith(".pptx")
    assert ppt_content.startswith(b"PK")

    shared = await service.create_share_link(ppt_report["report_id"], created_by="tester", expires_in_hours=24)
    assert shared is not None
    resolved = await service.resolve_share_link(shared["share_token"])
    assert resolved is not None
    assert resolved["report_id"] == ppt_report["report_id"]
    assert resolved["access_count"] == 1
    assert resolved["audit_flags"] == ["shared_access"]

    listed = await service.list_reports(report_type="weekly", limit=10)
    assert any(item["shared"] is True for item in listed)

    archived = await service.archive_report(ppt_report["report_id"])
    assert archived is not None
    assert archived["archived"] is True
    report = await service.get_report(ppt_report["report_id"])
    assert report is not None
    assert report["archived"] is True

    comparison = await service.compare_reports(pdf_report["report_id"], xlsx_report["report_id"])
    assert comparison is not None
    assert comparison["baseline_report_id"] == pdf_report["report_id"]
    assert comparison["target_report_id"] == xlsx_report["report_id"]
    assert any(item["metric"] == "task_count" for item in comparison["metric_differences"])


@pytest.mark.asyncio
async def test_report_center_state_survives_service_restart(tmp_path):
    state_path = tmp_path / "report-center-state.json"
    service = ReportCenterService(state_path=state_path)

    report = await service.generate(report_type="weekly", format="ppt", task_id="task-persist", params={"trend_change": 0.1})
    shared = await service.create_share_link(report["report_id"], created_by="tester", expires_in_hours=24)
    assert shared is not None
    archived = await service.archive_report(report["report_id"])
    assert archived is not None
    assert state_path.exists()

    restarted = ReportCenterService(state_path=state_path)

    restored_report = await restarted.get_report(report["report_id"])
    assert restored_report is not None
    assert restored_report["archived"] is True
    assert restored_report["shared"] is True
    assert restored_report["download_format"] == "ppt"

    restored_download = await restarted.build_download(report["report_id"])
    assert restored_download is not None
    content, media_type, filename = restored_download
    assert content.startswith(b"PK")
    assert media_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    assert filename.endswith(".pptx")

    restored_share = await restarted.resolve_share_link(shared["share_token"])
    assert restored_share is not None
    assert restored_share["report_id"] == report["report_id"]
    assert restored_share["access_count"] == 1


@pytest.mark.asyncio
async def test_report_center_service_honors_env_state_path(monkeypatch, tmp_path):
    state_path = tmp_path / "env-report-center-state.json"
    monkeypatch.setenv("REPORT_CENTER_STATE_PATH", str(state_path))

    service = ReportCenterService()
    report = await service.generate(report_type="weekly", format="pdf", task_id="task-env", params={"gmv": 123})

    assert report["report_id"]
    assert service.state_path == state_path
    assert state_path.exists()


@pytest.mark.asyncio
async def test_report_center_service_supports_custom_templates_and_metric_filters(tmp_path):
    service = ReportCenterService(state_path=tmp_path / "custom-report-state.json")

    templates = service.list_report_templates()
    assert any(item["name"] == "market_insight" for item in templates["templates"])
    assert any(item["key"] == "gmv" for item in templates["metric_catalog"])

    report = await service.generate_custom_report(
        report_type="weekly",
        format="html",
        task_id="task-custom-001",
        template_name="market_insight",
        title="分析师自定义报告",
        summary="聚焦蓝牙耳机趋势与竞品变化",
        sections=["趋势变化", "竞品动态", "行动建议"],
        metrics_filter=["gmv", "conversion_rate", "opportunities"],
        chart_keys=["sales_trend"],
        params={"gmv": 12345, "conversion_rate": 0.21, "opportunities": 8, "anomalies": 2},
    )

    assert report["title"] == "分析师自定义报告"
    assert report["summary"] == "聚焦蓝牙耳机趋势与竞品变化"
    assert sorted(report["metrics"].keys()) == ["conversion_rate", "gmv", "opportunities"]
    assert len(report["charts"]) == 1
    assert report["charts"][0]["chart_key"] == "sales_trend"
    assert report["metadata"]["template_name"] == "market_insight"
    assert report["metadata"]["customized"] is True
    assert "行动建议" in report["content"]
