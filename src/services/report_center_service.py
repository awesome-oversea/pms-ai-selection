from __future__ import annotations

import csv
import io
import json
import os
import secrets
import zipfile
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from numbers import Number
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from src.infrastructure.report_dashboard import Report, ReportEngine, ReportFormat, ReportStatus, ReportType
from src.services.channel_delivery_service import ChannelDeliveryService


class ReportCenterService:
    TEMPLATE_LIBRARY: dict[str, dict[str, Any]] = {
        "management_focus": {
            "name": "management_focus",
            "display_name": "管理层聚焦",
            "description": "聚焦经营指标、异常波动与执行建议。",
            "default_sections": ["经营摘要", "核心指标", "异常与风险", "行动建议"],
            "default_metrics": ["gmv", "completion_rate", "roi", "anomalies"],
            "default_charts": ["sales_trend", "category_dist"],
        },
        "market_insight": {
            "name": "market_insight",
            "display_name": "市场洞察",
            "description": "聚焦趋势、竞争态势与新增机会。",
            "default_sections": ["趋势变化", "竞品动态", "增长机会", "行动建议"],
            "default_metrics": ["gmv", "conversion_rate", "opportunities"],
            "default_charts": ["sales_trend"],
        },
        "finance_review": {
            "name": "finance_review",
            "display_name": "财务复盘",
            "description": "聚焦利润、成本和 ROI 表现。",
            "default_sections": ["利润表现", "成本结构", "ROI 复盘"],
            "default_metrics": ["gmv", "roi", "completion_rate"],
            "default_charts": ["sales_trend"],
        },
    }
    METRIC_CATALOG: list[dict[str, str]] = [
        {"key": "gmv", "label": "GMV", "description": "成交总额"},
        {"key": "completion_rate", "label": "Completion Rate", "description": "任务完成率"},
        {"key": "conversion_rate", "label": "Conversion Rate", "description": "转化率"},
        {"key": "opportunities", "label": "Opportunities", "description": "机会数量"},
        {"key": "anomalies", "label": "Anomalies", "description": "异常数量"},
        {"key": "roi", "label": "ROI", "description": "投资回报率"},
    ]
    CHART_CATALOG: list[dict[str, str]] = [
        {"key": "sales_trend", "chart_type": "line", "description": "销售趋势"},
        {"key": "category_dist", "chart_type": "pie", "description": "品类分布"},
    ]

    def __init__(self, engine: ReportEngine | None = None, *, state_path: str | Path | None = None) -> None:
        self.engine = engine or ReportEngine()
        configured_state_path = state_path or os.environ.get("REPORT_CENTER_STATE_PATH")
        self.state_path = Path(configured_state_path) if configured_state_path is not None else Path("artifacts") / "report_center" / "state.json"
        self._download_formats: dict[str, str] = {}
        self._share_links: dict[str, dict[str, Any]] = {}
        self._archived_reports: set[str] = set()
        self._archive_records: dict[str, dict[str, Any]] = {}
        self._load_state()

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        self._download_formats = dict(payload.get("download_formats") or {})
        self._share_links = dict(payload.get("share_links") or {})
        self._archived_reports = set(payload.get("archived_reports") or [])
        restored_reports: dict[str, Report] = {}
        for report_id, item in (payload.get("reports") or {}).items():
            try:
                restored_reports[report_id] = self._deserialize_report(item)
            except Exception:
                continue
        if restored_reports:
            self.engine._reports = restored_reports
            self._rebuild_engine_stats()

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        reports = getattr(self.engine, "_reports", {})
        payload = {
            "updated_at": datetime.now(UTC).isoformat(),
            "reports": {report_id: self._serialize_report(report) for report_id, report in reports.items()},
            "download_formats": self._download_formats,
            "share_links": self._share_links,
            "archived_reports": sorted(self._archived_reports),
            "archive_records": self._archive_records,
        }
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _serialize_report(report: Report) -> dict[str, Any]:
        return report.to_dict()

    @staticmethod
    def _deserialize_report(payload: dict[str, Any]) -> Report:
        return Report(
            report_id=payload["report_id"],
            report_type=ReportType(payload["report_type"]),
            title=payload["title"],
            content=payload.get("content", ""),
            summary=payload.get("summary", ""),
            format=ReportFormat(payload.get("format", ReportFormat.HTML.value)),
            status=ReportStatus(payload.get("status", ReportStatus.PENDING.value)),
            metrics=payload.get("metrics") or {},
            charts=payload.get("charts") or [],
            metadata=payload.get("metadata") or {},
            created_at=payload.get("created_at") or datetime.now(UTC).isoformat(),
            generated_at=payload.get("generated_at"),
        )

    def _rebuild_engine_stats(self) -> None:
        reports = getattr(self.engine, "_reports", {})
        by_type: defaultdict[str, int] = defaultdict(int)
        by_status: defaultdict[str, int] = defaultdict(int)
        for report in reports.values():
            by_type[report.report_type.value] += 1
            by_status[report.status.value] += 1
        self.engine._stats = {
            "total_reports": len(reports),
            "by_type": by_type,
            "by_status": by_status,
        }

    async def generate(self, *, report_type: str, format: str = "html", task_id: str | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        requested_format = format.lower()
        engine_report = await self.engine.generate_report(
            ReportType(report_type),
            format=self._map_format(requested_format),
            metrics=params or {},
        )
        payload = engine_report.to_dict()
        payload["task_id"] = task_id
        payload["format"] = requested_format
        payload["download_url"] = f"/api/v1/reports/{payload['report_id']}/download"
        payload["download_format"] = requested_format
        self._download_formats[payload["report_id"]] = requested_format
        self._save_state()
        return payload

    def list_report_templates(self) -> dict[str, Any]:
        return {
            "templates": list(self.TEMPLATE_LIBRARY.values()),
            "metric_catalog": list(self.METRIC_CATALOG),
            "chart_catalog": list(self.CHART_CATALOG),
            "supported_formats": ["html", "pdf", "xlsx", "pptx", "excel", "csv"],
        }

    async def generate_custom_report(
        self,
        *,
        report_type: str,
        format: str = "html",
        task_id: str | None = None,
        template_name: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        sections: list[str] | None = None,
        metrics_filter: list[str] | None = None,
        chart_keys: list[str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        selected_template_name = template_name or "management_focus"
        template = self.TEMPLATE_LIBRARY.get(selected_template_name)
        if template is None:
            raise ValueError(f"Unknown report template: {selected_template_name}")

        payload = await self.generate(
            report_type=report_type,
            format=format,
            task_id=task_id,
            params=params,
        )
        report = await self.engine.get_report(payload["report_id"])
        if report is None:
            payload["metadata"] = {
                "template_name": selected_template_name,
                "sections": sections or template["default_sections"],
                "metrics_filter": metrics_filter or template["default_metrics"],
                "chart_keys": chart_keys or template["default_charts"],
                "customized": True,
            }
            return payload

        filtered_metrics = dict(report.metrics or {})
        effective_metric_keys = list(metrics_filter or template["default_metrics"])
        if effective_metric_keys:
            allowed_metric_keys = set(effective_metric_keys)
            filtered_metrics = {
                key: value for key, value in filtered_metrics.items() if key in allowed_metric_keys
            }

        filtered_charts = list(report.charts or [])
        effective_chart_keys = list(chart_keys or template["default_charts"])
        if effective_chart_keys:
            allowed_chart_keys = set(effective_chart_keys)
            filtered_charts = [
                chart for chart in filtered_charts if (chart.get("chart_key") or chart.get("chart_id")) in allowed_chart_keys
            ]

        resolved_sections = list(sections or template["default_sections"])
        resolved_summary = summary or report.summary
        resolved_title = title or report.title

        report.title = resolved_title
        report.summary = resolved_summary
        report.metrics = filtered_metrics
        report.charts = filtered_charts
        report.metadata = {
            **(report.metadata or {}),
            "template_name": selected_template_name,
            "template_display_name": template["display_name"],
            "sections": resolved_sections,
            "metrics_filter": effective_metric_keys,
            "chart_keys": effective_chart_keys,
            "customized": True,
        }
        report.content = self._build_custom_content(
            title=resolved_title,
            summary=resolved_summary,
            sections=resolved_sections,
            metrics=filtered_metrics,
            charts=filtered_charts,
        )

        customized_payload = report.to_dict()
        customized_payload["task_id"] = task_id
        customized_payload["format"] = format.lower()
        customized_payload["download_url"] = f"/api/v1/reports/{report.report_id}/download"
        customized_payload["download_format"] = format.lower()
        self._download_formats[report.report_id] = format.lower()
        self._save_state()
        return customized_payload

    async def list_reports(
        self,
        report_type: str | None = None,
        limit: int = 20,
        *,
        created_after: str | None = None,
        created_before: str | None = None,
    ) -> list[dict[str, Any]]:
        items = await self.engine.list_reports(report_type=ReportType(report_type) if report_type else None, limit=limit)
        results: list[dict[str, Any]] = []
        after_dt = datetime.fromisoformat(created_after) if created_after else None
        before_dt = datetime.fromisoformat(created_before) if created_before else None
        for item in items:
            if after_dt and item.generated_at < after_dt:
                continue
            if before_dt and item.generated_at > before_dt:
                continue
            payload = item.to_dict()
            payload["download_format"] = self._download_formats.get(item.report_id, item.format.value)
            payload["download_url"] = f"/api/v1/reports/{item.report_id}/download"
            payload["archived"] = item.report_id in self._archived_reports
            payload["archive_record"] = self._archive_records.get(item.report_id)
            payload["shared"] = any(link.get("report_id") == item.report_id for link in self._share_links.values())
            payload["audit_flags"] = ["downloadable", "shareable", "archivable"]
            results.append(payload)
        return results[:limit]

    async def get_report(self, report_id: str) -> dict[str, Any] | None:
        report = await self.engine.get_report(report_id)
        if report is None:
            return None
        payload = report.to_dict()
        payload["download_format"] = self._download_formats.get(report_id, report.format.value)
        payload["download_url"] = f"/api/v1/reports/{report_id}/download"
        payload["archived"] = report_id in self._archived_reports
        payload["shared"] = any(link.get("report_id") == report_id for link in self._share_links.values())
        payload["audit_flags"] = ["downloadable", "shareable", "archivable"]
        return payload

    async def build_download(self, report_id: str) -> tuple[bytes, str, str] | None:
        report = await self.engine.get_report(report_id)
        if report is None:
            return None
        requested_format = self._download_formats.get(report_id, report.format.value)
        if requested_format == "pdf":
            content = self._build_pdf_bytes(report)
            return content, "application/pdf", f"{report.report_id}.pdf"
        if requested_format in {"excel", "csv"}:
            content = self._build_csv_bytes(report)
            return content, "text/csv; charset=utf-8", f"{report.report_id}.csv"
        if requested_format == "xlsx":
            content = self._build_xlsx_bytes(report)
            return content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{report.report_id}.xlsx"
        if requested_format in {"ppt", "pptx"}:
            content = self._build_pptx_bytes(report)
            return content, "application/vnd.openxmlformats-officedocument.presentationml.presentation", f"{report.report_id}.pptx"
        content = report.content.encode("utf-8")
        return content, "text/html; charset=utf-8", f"{report.report_id}.html"

    async def create_share_link(self, report_id: str, *, created_by: str, expires_in_hours: int = 24) -> dict[str, Any] | None:
        report = await self.engine.get_report(report_id)
        if report is None:
            return None
        token = secrets.token_urlsafe(24)
        expires_at = datetime.now(UTC) + timedelta(hours=max(1, expires_in_hours))
        self._share_links[token] = {
            "report_id": report_id,
            "created_by": created_by,
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": expires_at.isoformat(),
            "access_count": 0,
        }
        self._save_state()
        return {
            "share_token": token,
            "share_url": f"/api/v1/reports/share/{token}",
            "report_id": report_id,
            "expires_at": expires_at.isoformat(),
        }

    async def resolve_share_link(self, share_token: str) -> dict[str, Any] | None:
        share = self._share_links.get(share_token)
        if share is None:
            return None
        expires_at = datetime.fromisoformat(share["expires_at"])
        if expires_at < datetime.now(UTC):
            self._share_links.pop(share_token, None)
            self._save_state()
            return None
        report = await self.get_report(share["report_id"])
        if report is None:
            return None
        share["access_count"] += 1
        self._save_state()
        return {
            "share_token": share_token,
            "report_id": share["report_id"],
            "share_url": f"/api/v1/reports/share/{share_token}",
            "download_url": report["download_url"],
            "expires_at": share["expires_at"],
            "access_count": share["access_count"],
            "audit_flags": ["shared_access"],
            "report": report,
        }

    async def share_report_to_channel(
        self,
        report_id: str,
        *,
        channel: str,
        webhook_url: str,
        created_by: str,
        expires_in_hours: int = 24,
    ) -> dict[str, Any] | None:
        report = await self.get_report(report_id)
        if report is None:
            return None
        share = await self.create_share_link(report_id, created_by=created_by, expires_in_hours=expires_in_hours)
        if share is None:
            return None
        delivery_service = ChannelDeliveryService()
        delivery = await delivery_service.share_report_link(
            channel=channel,
            webhook_url=webhook_url,
            report_title=str(report.get("title") or f"Report {report_id}"),
            report_summary=str(report.get("summary") or ""),
            share_url=share["share_url"],
        )
        return {
            "report_id": report_id,
            "channel": channel,
            "share": share,
            "delivery": delivery,
        }

    @staticmethod
    def _map_format(format_name: str) -> ReportFormat:
        if format_name == "pdf":
            return ReportFormat.PDF
        if format_name in {"excel", "csv", "xlsx"}:
            return ReportFormat.EXCEL
        return ReportFormat.HTML

    @staticmethod
    def _build_csv_bytes(report: Any) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["title", report.title])
        writer.writerow(["summary", report.summary])
        writer.writerow([])
        writer.writerow(["metric", "value"])
        for key, value in (report.metrics or {}).items():
            writer.writerow([key, value])
        return buffer.getvalue().encode("utf-8-sig")

    @staticmethod
    def _xlsx_inline_cell(cell_ref: str, value: Any) -> str:
        text = escape("" if value is None else str(value))
        return f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'

    @staticmethod
    def _xlsx_number_cell(cell_ref: str, value: Number) -> str:
        return f'<c r="{cell_ref}"><v>{value}</v></c>'

    @classmethod
    def _xlsx_cell(cls, cell_ref: str, value: Any) -> str:
        if isinstance(value, Number) and not isinstance(value, bool):
            return cls._xlsx_number_cell(cell_ref, value)
        return cls._xlsx_inline_cell(cell_ref, value)

    @classmethod
    def _build_xlsx_bytes(cls, report: Any) -> bytes:
        rows: list[tuple[int, list[str]]] = [
            (1, [cls._xlsx_inline_cell("A1", "title"), cls._xlsx_inline_cell("B1", report.title)]),
            (2, [cls._xlsx_inline_cell("A2", "summary"), cls._xlsx_inline_cell("B2", report.summary)]),
            (4, [cls._xlsx_inline_cell("A4", "metric"), cls._xlsx_inline_cell("B4", "value")]),
        ]
        row_index = 5
        for key, value in (report.metrics or {}).items():
            rows.append((row_index, [cls._xlsx_inline_cell(f"A{row_index}", key), cls._xlsx_cell(f"B{row_index}", value)]))
            row_index += 1
        sheet_rows = "".join(f'<row r="{idx}">{"".join(cells)}</row>' for idx, cells in rows)
        sheet_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData>'
            f'{sheet_rows}'
            '</sheetData>'
            '</worksheet>'
        )
        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>'
        )
        workbook_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        )
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        )
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            '</Types>'
        )
        package_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            '</Relationships>'
        )
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        core_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{escape(report.title)}</dc:title>'
            '<dc:creator>OpenCoWork</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
            '</cp:coreProperties>'
        )
        app_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            '<Application>OpenCoWork</Application>'
            '</Properties>'
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", package_rels)
            zf.writestr("docProps/core.xml", core_xml)
            zf.writestr("docProps/app.xml", app_xml)
            zf.writestr("xl/workbook.xml", workbook_xml)
            zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
            zf.writestr("xl/styles.xml", styles_xml)
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        return buffer.getvalue()

    @staticmethod
    def _build_pptx_bytes(report: Any) -> bytes:
        title = escape(report.title)
        body_text = escape(f"{report.summary}\n\n{report.content[:1200]}")
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>'
            '<Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>'
            '<Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>'
            '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
            '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
            '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
            '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            '</Types>'
        )
        package_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            '</Relationships>'
        )
        app_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            '<Application>OpenCoWork</Application><Slides>1</Slides><Notes>0</Notes><HiddenSlides>0</HiddenSlides>'
            '<MMClips>0</MMClips><PresentationFormat>On-screen Show</PresentationFormat>'
            '</Properties>'
        )
        core_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{title}</dc:title><dc:creator>OpenCoWork</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
            '</cp:coreProperties>'
        )
        presentation_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
            '<p:sldIdLst><p:sldId id="256" r:id="rId7"/></p:sldIdLst>'
            '<p:sldSz cx="9144000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/>'
            '</p:presentation>'
        )
        presentation_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/>'
            '<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/>'
            '<Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>'
            '</Relationships>'
        )
        pres_props = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'
        )
        view_props = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:normalViewPr/><p:slideViewPr/><p:notesTextViewPr/><p:gridSpacing cx="72008" cy="72008"/>'
            '</p:viewPr>'
        )
        table_styles = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>'
        )
        theme_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="OpenCoWork Theme">'
            '<a:themeElements>'
            '<a:clrScheme name="OpenCoWork Colors">'
            '<a:dk1><a:srgbClr val="000000"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
            '<a:dk2><a:srgbClr val="1F497D"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2>'
            '<a:accent1><a:srgbClr val="4F81BD"/></a:accent1><a:accent2><a:srgbClr val="C0504D"/></a:accent2>'
            '<a:accent3><a:srgbClr val="9BBB59"/></a:accent3><a:accent4><a:srgbClr val="8064A2"/></a:accent4>'
            '<a:accent5><a:srgbClr val="4BACC6"/></a:accent5><a:accent6><a:srgbClr val="F79646"/></a:accent6>'
            '<a:hlink><a:srgbClr val="0000FF"/></a:hlink><a:folHlink><a:srgbClr val="800080"/></a:folHlink>'
            '</a:clrScheme>'
            '<a:fontScheme name="OpenCoWork Fonts">'
            '<a:majorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
            '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
            '</a:fontScheme>'
            '<a:fmtScheme name="OpenCoWork Format">'
            '<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
            '<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln></a:lnStyleLst>'
            '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
            '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
            '</a:fmtScheme>'
            '</a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/>'
            '</a:theme>'
        )
        slide_master_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:cSld name="OpenCoWork Master"><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title Placeholder 1"/><p:cNvSpPr/><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>'
            '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Content Placeholder 2"/><p:cNvSpPr/><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>'
            '</p:spTree></p:cSld>'
            '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            '<p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst>'
            '<p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>'
            '</p:sldMaster>'
        )
        slide_master_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
            '</Relationships>'
        )
        slide_layout_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="titleAndContent" preserve="1">'
            '<p:cSld name="Title and Content"><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title 1"/><p:cNvSpPr/><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>'
            '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Content Placeholder 2"/><p:cNvSpPr/><p:nvPr><p:ph idx="1"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>'
            '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
            '</p:sldLayout>'
        )
        slide1_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title 1"/><p:cNvSpPr/><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:spPr/>'
            '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>' + title + '</a:t></a:r></a:p></p:txBody></p:sp>'
            '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Content Placeholder 2"/><p:cNvSpPr/><p:nvPr><p:ph idx="1"/></p:nvPr></p:nvSpPr><p:spPr/>'
            '<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/><a:p><a:r><a:t>' + body_text + '</a:t></a:r></a:p></p:txBody></p:sp>'
            '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
            '</p:sld>'
        )
        slide1_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '</Relationships>'
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", package_rels)
            zf.writestr("docProps/app.xml", app_xml)
            zf.writestr("docProps/core.xml", core_xml)
            zf.writestr("ppt/presentation.xml", presentation_xml)
            zf.writestr("ppt/_rels/presentation.xml.rels", presentation_rels)
            zf.writestr("ppt/presProps.xml", pres_props)
            zf.writestr("ppt/viewProps.xml", view_props)
            zf.writestr("ppt/tableStyles.xml", table_styles)
            zf.writestr("ppt/theme/theme1.xml", theme_xml)
            zf.writestr("ppt/slideMasters/slideMaster1.xml", slide_master_xml)
            zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", slide_master_rels)
            zf.writestr("ppt/slideLayouts/slideLayout1.xml", slide_layout_xml)
            zf.writestr("ppt/slides/slide1.xml", slide1_xml)
            zf.writestr("ppt/slides/_rels/slide1.xml.rels", slide1_rels)
        return buffer.getvalue()

    async def compare_reports(self, baseline_report_id: str, target_report_id: str) -> dict[str, Any] | None:
        baseline = await self.engine.get_report(baseline_report_id)
        target = await self.engine.get_report(target_report_id)
        if baseline is None or target is None:
            return None

        baseline_metrics = baseline.metrics or {}
        target_metrics = target.metrics or {}
        metric_keys = sorted(set(baseline_metrics.keys()) | set(target_metrics.keys()))
        metric_diffs: list[dict[str, Any]] = []
        for key in metric_keys:
            before = baseline_metrics.get(key)
            after = target_metrics.get(key)
            diff = None
            if isinstance(before, Number) and isinstance(after, Number):
                diff = round(float(after) - float(before), 4)
            metric_diffs.append({
                "metric": key,
                "baseline": before,
                "target": after,
                "diff": diff,
            })

        baseline_summary = baseline.summary or ""
        target_summary = target.summary or ""
        baseline_lines = {line.strip() for line in baseline_summary.splitlines() if line.strip()}
        target_lines = {line.strip() for line in target_summary.splitlines() if line.strip()}
        added_summary = sorted(target_lines - baseline_lines)
        removed_summary = sorted(baseline_lines - target_lines)

        return {
            "baseline_report_id": baseline_report_id,
            "target_report_id": target_report_id,
            "baseline": {
                "title": baseline.title,
                "report_type": baseline.report_type.value,
                "format": self._download_formats.get(baseline_report_id, baseline.format.value),
                "archived": baseline_report_id in self._archived_reports,
                "archive_record": self._archive_records.get(baseline_report_id),
            },
            "target": {
                "title": target.title,
                "report_type": target.report_type.value,
                "format": self._download_formats.get(target_report_id, target.format.value),
                "archived": target_report_id in self._archived_reports,
                "archive_record": self._archive_records.get(target_report_id),
            },
            "metric_differences": metric_diffs,
            "summary_diff": {
                "added": added_summary,
                "removed": removed_summary,
            },
            "archive_context": {
                "baseline_archived": baseline_report_id in self._archived_reports,
                "target_archived": target_report_id in self._archived_reports,
                "archived_report_total": len(self._archived_reports),
            },
            "audit_flags": ["comparable", "archivable"],
        }

    async def archive_report(self, report_id: str) -> dict[str, Any] | None:
        report = await self.engine.get_report(report_id)
        if report is None:
            return None
        self._archived_reports.add(report_id)
        archive_record = {
            "report_id": report_id,
            "title": report.title,
            "report_type": report.report_type.value,
            "format": self._download_formats.get(report_id, report.format.value),
            "archived_at": datetime.now(UTC).isoformat(),
            "generated_at": report.generated_at,
            "created_at": report.created_at,
            "metrics_snapshot": report.metrics or {},
        }
        self._archive_records[report_id] = archive_record
        self._save_state()
        return {
            "report_id": report_id,
            "archived": True,
            "status": "archived",
            "archive_record": archive_record,
            "audit_flags": ["archived"],
        }

    async def list_archived_reports(self, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        items = sorted(self._archive_records.values(), key=lambda item: item.get("archived_at") or "", reverse=True)
        total = len(items)
        paginated = items[offset: offset + limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": paginated,
        }

    async def get_archive_record(self, report_id: str) -> dict[str, Any] | None:
        return self._archive_records.get(report_id)

    @staticmethod
    def _build_custom_content(
        *,
        title: str,
        summary: str,
        sections: list[str],
        metrics: dict[str, Any],
        charts: list[dict[str, Any]],
    ) -> str:
        lines = [f"# {title}", "", summary]
        if metrics:
            lines.extend(["", "## 核心指标"])
            for key, value in metrics.items():
                lines.append(f"- {key}: {value}")
        if charts:
            lines.extend(["", "## 图表视图"])
            for chart in charts:
                chart_key = chart.get("chart_key") or chart.get("chart_id") or "chart"
                chart_title = chart.get("title") or chart_key
                lines.append(f"- {chart_title} ({chart_key})")
        for section in sections:
            lines.extend(["", f"## {section}", f"- {section} 内容已根据当前模板生成。"])
        return "\n".join(lines)

    @staticmethod
    def _pdf_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    @classmethod
    def _build_pdf_bytes(cls, report: Any) -> bytes:
        lines = [str(report.title or "报告"), "", str(report.summary or "")]
        metrics = report.metrics or {}
        if metrics:
            lines.append("")
            lines.append("关键指标:")
            for key, value in metrics.items():
                lines.append(f"- {key}: {value}")
        charts = report.charts or []
        if charts:
            lines.append("")
            lines.append("图表摘要:")
            for chart in charts[:10]:
                if isinstance(chart, dict):
                    lines.append(f"- {chart.get('title') or chart.get('name') or 'chart'} ({chart.get('chart_type') or chart.get('type') or 'unknown'})")
        content_text = str(report.content or "")
        if content_text:
            lines.append("")
            lines.extend(content_text.splitlines()[:40])

        sanitized_lines = [cls._pdf_escape(line)[:180] for line in lines]
        text_commands = ["BT", "/F1 12 Tf", "50 790 Td", "14 TL"]
        first_line = True
        for line in sanitized_lines:
            if first_line:
                text_commands.append(f"({line}) Tj")
                first_line = False
            else:
                text_commands.append(f"T* ({line}) Tj")
        text_commands.append("ET")
        stream = "\n".join(text_commands).encode("utf-8")

        objects = [
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
            b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
            f"5 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream\nendobj\n",
        ]

        buffer = io.BytesIO()
        buffer.write(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(buffer.tell())
            buffer.write(obj)
        startxref = buffer.tell()
        buffer.write(f"xref\n0 {len(offsets)}\n".encode())
        buffer.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            buffer.write(f"{offset:010d} 00000 n \n".encode())
        buffer.write(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF".encode())
        return buffer.getvalue()
