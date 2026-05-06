"""D126-D130 单元测试: 最终交付与知识转移"""


import pytest
from src.infrastructure.delivery import (
    AcceptanceCategory,
    AcceptanceCheck,
    DeliveryManager,
    Document,
    DocumentCategory,
    DocumentStatus,
    KnowledgeTransfer,
    ProjectSummary,
    ReviewItem,
    ReviewManager,
    ReviewStatus,
    TransferStatus,
)


class TestDocument:
    """测试文档"""

    def test_document_creation(self):
        doc = Document(
            document_id="DOC_001",
            title="系统架构图",
            category=DocumentCategory.ARCHITECTURE,
        )
        assert doc.document_id == "DOC_001"
        assert doc.status == DocumentStatus.DRAFT

    def test_document_to_dict(self):
        doc = Document(
            document_id="DOC_001",
            title="API文档",
            category=DocumentCategory.API,
            version="v2.0",
            pages=50,
        )
        d = doc.to_dict()
        assert d["version"] == "v2.0"


class TestKnowledgeTransfer:
    """测试知识转移"""

    def test_transfer_creation(self):
        transfer = KnowledgeTransfer(
            transfer_id="TRANSFER_001",
            module="架构设计",
            recipient="技术负责人",
        )
        assert transfer.transfer_id == "TRANSFER_001"
        assert transfer.status == TransferStatus.PENDING

    def test_transfer_to_dict(self):
        transfer = KnowledgeTransfer(
            transfer_id="TRANSFER_001",
            module="核心业务",
            recipient="开发团队",
            method="Pair Programming",
        )
        d = transfer.to_dict()
        assert d["method"] == "Pair Programming"


class TestReviewItem:
    """测试复盘项"""

    def test_item_creation(self):
        item = ReviewItem(
            item_id="REVIEW_001",
            dimension="目标达成",
        )
        assert item.item_id == "REVIEW_001"
        assert item.score == 0

    def test_item_to_dict(self):
        item = ReviewItem(
            item_id="REVIEW_001",
            dimension="质量管理",
            score=85,
            findings="质量良好",
        )
        d = item.to_dict()
        assert d["score"] == 85


class TestAcceptanceCheck:
    """测试验收检查"""

    def test_check_creation(self):
        check = AcceptanceCheck(
            check_id="CHECK_001",
            category=AcceptanceCategory.FUNCTIONALITY,
        )
        assert check.check_id == "CHECK_001"
        assert check.passed is False

    def test_check_to_dict(self):
        check = AcceptanceCheck(
            check_id="CHECK_001",
            category=AcceptanceCategory.SECURITY,
            passed=True,
            details="无高危漏洞",
        )
        d = check.to_dict()
        assert d["passed"] is True


class TestProjectSummary:
    """测试项目总结"""

    def test_summary_creation(self):
        summary = ProjectSummary()
        assert summary.total_days == 130
        assert summary.agent_count == 4

    def test_summary_to_dict(self):
        summary = ProjectSummary(
            total_days=130,
            total_tasks=120,
            code_lines=50000,
        )
        d = summary.to_dict()
        assert d["total_days"] == 130


class TestDeliveryManager:
    """测试交付管理器(D126-D127)"""

    def setup_method(self):
        self.delivery = DeliveryManager()

    @pytest.mark.asyncio
    async def test_create_document(self):
        doc = await self.delivery.create_document(
            title="系统架构图",
            category=DocumentCategory.ARCHITECTURE,
            pages=30,
            author="架构师",
        )
        assert doc.document_id.startswith("DOC_")

    @pytest.mark.asyncio
    async def test_approve_document(self):
        doc = await self.delivery.create_document(
            "API文档",
            DocumentCategory.API,
        )
        result = await self.delivery.approve_document(doc.document_id, "审核员")
        assert result.status == DocumentStatus.APPROVED

    @pytest.mark.asyncio
    async def test_create_transfer(self):
        transfer = await self.delivery.create_transfer(
            module="架构设计",
            recipient="技术负责人",
            method="代码走读",
        )
        assert transfer.transfer_id.startswith("TRANSFER_")

    @pytest.mark.asyncio
    async def test_complete_transfer(self):
        created = await self.delivery.create_transfer("核心业务", "开发团队")
        result = await self.delivery.complete_transfer(created.transfer_id, "完成")
        assert result.status == TransferStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_finalize_delivery(self):
        result = await self.delivery.finalize_delivery()
        assert result["status"] == "completed"
        assert result["transfers"] == 4

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.delivery.create_document("文档", DocumentCategory.USER_GUIDE)
        stats = self.delivery.get_stats()
        assert stats["total_documents"] == 1


class TestReviewManager:
    """测试评审管理器(D128-D130)"""

    def setup_method(self):
        self.review = ReviewManager()

    @pytest.mark.asyncio
    async def test_create_review_item(self):
        item = await self.review.create_review_item(
            dimension="目标达成",
            content="项目目标完成情况",
        )
        assert item.item_id.startswith("REVIEW_")
        assert item.score >= 70

    @pytest.mark.asyncio
    async def test_conduct_review(self):
        result = await self.review.conduct_review()
        assert "items" in result
        assert len(result["items"]) == 6
        assert "average_score" in result

    @pytest.mark.asyncio
    async def test_create_acceptance_check(self):
        check = await self.review.create_acceptance_check(AcceptanceCategory.FUNCTIONALITY)
        assert check.check_id.startswith("CHECK_")
        assert check.passed in [True, False]

    @pytest.mark.asyncio
    async def test_run_acceptance_checks(self):
        result = await self.review.run_acceptance_checks()
        assert "checks" in result
        assert len(result["checks"]) == 6
        assert "pass_rate" in result

    @pytest.mark.asyncio
    async def test_conduct_final_review(self):
        result = await self.review.conduct_final_review()
        assert "review" in result
        assert "acceptance" in result
        assert "project_summary" in result
        assert "final_status" in result

    def test_get_project_summary(self):
        summary = self.review.get_project_summary()
        assert summary["total_days"] == 130
        assert len(summary["milestones"]) == 4

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.review.conduct_final_review()
        stats = self.review.get_stats()
        assert stats["total_reviews"] == 6
        assert stats["total_checks"] == 6


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_delivery_workflow(self):
        delivery = DeliveryManager()
        review = ReviewManager()

        for category in [DocumentCategory.ARCHITECTURE, DocumentCategory.API, DocumentCategory.OPERATIONS]:
            doc = await delivery.create_document(f"{category.value}文档", category)
            await delivery.approve_document(doc.document_id, "审核员")

        delivery_result = await delivery.finalize_delivery()

        review_result = await review.conduct_final_review()

        assert delivery_result["status"] == "completed"
        assert review_result["final_status"] in [ReviewStatus.PASSED.value, ReviewStatus.CONDITIONAL.value]
        assert review_result["project_summary"]["total_days"] == 130


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
