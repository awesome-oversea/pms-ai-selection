"""D71-D75 单元测试: WMS仓储 + CRM客户 + FMS财务"""


import pytest
from src.infrastructure.wms_crm_fms import (
    Alert,
    AlertLevel,
    AlertType,
    CRMManager,
    Customer,
    CustomerTier,
    FinancialRecord,
    FMSManager,
    Inventory,
    WMSManager,
)


class TestInventory:
    """测试库存"""

    def test_inventory_creation(self):
        inv = Inventory(
            sku="SKU_001",
            product_name="储能电源",
            warehouse_id="WH_001",
            total_quantity=100,
        )
        assert inv.sku == "SKU_001"
        assert inv.total_quantity == 100

    def test_inventory_to_dict(self):
        inv = Inventory(
            sku="SKU_001",
            product_name="储能电源",
            warehouse_id="WH_001",
            safety_stock=20,
        )
        d = inv.to_dict()
        assert d["sku"] == "SKU_001"
        assert d["safety_stock"] == 20


class TestAlert:
    """测试预警"""

    def test_alert_creation(self):
        alert = Alert(
            alert_id="ALT_001",
            alert_type=AlertType.LOW_STOCK,
            alert_level=AlertLevel.HIGH,
            sku="SKU_001",
            product_name="储能电源",
            message="低库存",
            current_value=5,
            threshold=20,
            suggestion="补货",
        )
        assert alert.alert_type == AlertType.LOW_STOCK
        assert alert.acknowledged is False

    def test_alert_to_dict(self):
        alert = Alert(
            alert_id="ALT_001",
            alert_type=AlertType.OUT_OF_STOCK,
            alert_level=AlertLevel.HIGH,
            sku="SKU_001",
            product_name="储能电源",
            message="缺货",
            current_value=0,
            threshold=10,
            suggestion="立即补货",
        )
        d = alert.to_dict()
        assert d["alert_type"] == "out_of_stock"


class TestCustomer:
    """测试客户"""

    def test_customer_creation(self):
        customer = Customer(
            customer_id="CUST_001",
            name="张三",
            email="zhangsan@example.com",
        )
        assert customer.customer_id == "CUST_001"
        assert customer.tier == CustomerTier.BRONZE

    def test_calculate_rfm(self):
        customer = Customer(
            customer_id="CUST_001",
            name="张三",
            recency_days=15,
            frequency=20,
            monetary=10000,
        )
        customer.calculate_rfm()
        assert customer.rfm_score > 0

    def test_determine_tier_platinum(self):
        customer = Customer(
            customer_id="CUST_001",
            name="张三",
            total_spend=60000,
        )
        tier = customer.determine_tier()
        assert tier == CustomerTier.PLATINUM

    def test_determine_tier_gold(self):
        customer = Customer(
            customer_id="CUST_001",
            name="张三",
            total_spend=25000,
        )
        tier = customer.determine_tier()
        assert tier == CustomerTier.GOLD

    def test_customer_to_dict(self):
        customer = Customer(
            customer_id="CUST_001",
            name="张三",
            tier=CustomerTier.GOLD,
        )
        d = customer.to_dict()
        assert d["tier"] == "gold"


class TestFinancialRecord:
    """测试财务记录"""

    def test_record_creation(self):
        record = FinancialRecord(
            record_id="COST_001",
            record_type="cost",
            product_id="P001",
            order_id="O001",
            amount=1000.0,
            category="purchase",
            description="采购成本",
        )
        assert record.record_type == "cost"
        assert record.amount == 1000.0

    def test_record_to_dict(self):
        record = FinancialRecord(
            record_id="REV_001",
            record_type="revenue",
            product_id="P001",
            order_id=None,
            amount=2000.0,
            category="revenue",
            description="销售收入",
        )
        d = record.to_dict()
        assert d["record_type"] == "revenue"


class TestWMSManager:
    """测试WMS管理器(D71-D72)"""

    def setup_method(self):
        self.wms = WMSManager()

    @pytest.mark.asyncio
    async def test_create_inventory(self):
        inv = await self.wms.create_inventory(
            sku="SKU_001",
            product_name="储能电源",
            total_quantity=100,
        )
        assert inv.sku == "SKU_001"
        assert inv.total_quantity == 100

    @pytest.mark.asyncio
    async def test_get_inventory(self):
        await self.wms.create_inventory(sku="SKU_001", product_name="储能电源")
        inv = await self.wms.get_inventory("SKU_001")
        assert inv.product_name == "储能电源"

    @pytest.mark.asyncio
    async def test_stock_in(self):
        await self.wms.create_inventory(sku="SKU_001", product_name="储能电源", total_quantity=50)
        result = await self.wms.stock_in("SKU_001", 30)
        assert result["success"] is True
        inv = await self.wms.get_inventory("SKU_001")
        assert inv.total_quantity == 80

    @pytest.mark.asyncio
    async def test_stock_out(self):
        await self.wms.create_inventory(sku="SKU_001", product_name="储能电源", total_quantity=100)
        result = await self.wms.stock_out("SKU_001", 30)
        assert result["success"] is True
        inv = await self.wms.get_inventory("SKU_001")
        assert inv.total_quantity == 70

    @pytest.mark.asyncio
    async def test_stock_out_insufficient(self):
        await self.wms.create_inventory(sku="SKU_001", product_name="储能电源", total_quantity=10)
        result = await self.wms.stock_out("SKU_001", 50)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_check_alerts_low_stock(self):
        await self.wms.create_inventory(
            sku="SKU_001",
            product_name="储能电源",
            total_quantity=5,
            safety_stock=20,
        )
        alerts = await self.wms.check_alerts()
        low_stock_alerts = [a for a in alerts if a.alert_type == AlertType.LOW_STOCK]
        assert len(low_stock_alerts) == 1

    @pytest.mark.asyncio
    async def test_check_alerts_out_of_stock(self):
        await self.wms.create_inventory(
            sku="SKU_001",
            product_name="储能电源",
            total_quantity=0,
            safety_stock=10,
        )
        alerts = await self.wms.check_alerts()
        oos_alerts = [a for a in alerts if a.alert_type == AlertType.OUT_OF_STOCK]
        assert len(oos_alerts) == 1

    @pytest.mark.asyncio
    async def test_acknowledge_alert(self):
        await self.wms.create_inventory(
            sku="SKU_001",
            product_name="储能电源",
            total_quantity=5,
            safety_stock=20,
        )
        alerts = await self.wms.check_alerts()
        if alerts:
            alert = await self.wms.acknowledge_alert(alerts[0].alert_id)
            assert alert.acknowledged is True

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.wms.create_inventory(sku="SKU_001", product_name="储能电源")
        stats = self.wms.get_stats()
        assert stats["total_skus"] == 1


class TestCRMManager:
    """测试CRM管理器(D73-D74)"""

    def setup_method(self):
        self.crm = CRMManager()

    @pytest.mark.asyncio
    async def test_create_customer(self):
        customer = await self.crm.create_customer(
            name="张三",
            email="zhangsan@example.com",
        )
        assert customer.customer_id.startswith("CUST_")
        assert customer.name == "张三"

    @pytest.mark.asyncio
    async def test_get_customer(self):
        created = await self.crm.create_customer(name="张三")
        customer = await self.crm.get_customer(created.customer_id)
        assert customer.name == "张三"

    @pytest.mark.asyncio
    async def test_update_customer_metrics(self):
        customer = await self.crm.create_customer(name="张三")
        updated = await self.crm.update_customer_metrics(
            customer.customer_id,
            recency_days=10,
            frequency=15,
            monetary=8000,
        )
        assert updated.recency_days == 10
        assert updated.frequency == 15
        assert updated.tier == CustomerTier.SILVER

    @pytest.mark.asyncio
    async def test_segment_customers(self):
        c1 = await self.crm.create_customer(name="客户A")
        await self.crm.update_customer_metrics(c1.customer_id, recency_days=5, frequency=30, monetary=50000)

        c2 = await self.crm.create_customer(name="客户B")
        await self.crm.update_customer_metrics(c2.customer_id, recency_days=60, frequency=5, monetary=1000)

        segments = await self.crm.segment_customers()
        assert "high_value" in segments
        assert "low_value" in segments

    @pytest.mark.asyncio
    async def test_list_customers_by_tier(self):
        c1 = await self.crm.create_customer(name="客户A")
        await self.crm.update_customer_metrics(c1.customer_id, monetary=30000)

        customers = await self.crm.list_customers(tier=CustomerTier.GOLD)
        assert len(customers) == 1

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.crm.create_customer(name="张三")
        stats = self.crm.get_stats()
        assert stats["total_customers"] == 1


class TestFMSManager:
    """测试FMS管理器(D75)"""

    def setup_method(self):
        self.fms = FMSManager()

    @pytest.mark.asyncio
    async def test_record_cost(self):
        record = await self.fms.record_cost(
            product_id="P001",
            amount=500.0,
            category="purchase",
            description="采购成本",
        )
        assert record.record_type == "cost"
        assert record.amount == 500.0

    @pytest.mark.asyncio
    async def test_record_revenue(self):
        record = await self.fms.record_revenue(
            product_id="P001",
            amount=1000.0,
            description="销售收入",
        )
        assert record.record_type == "revenue"

    @pytest.mark.asyncio
    async def test_calculate_profit(self):
        await self.fms.record_cost("P001", 400.0, "purchase")
        await self.fms.record_cost("P001", 50.0, "logistics")
        await self.fms.record_cost("P001", 30.0, "platform")
        await self.fms.record_revenue("P001", 800.0)

        summary = await self.fms.calculate_profit("P001", "储能电源")
        assert summary.total_revenue == 800.0
        assert summary.total_cost == 480.0
        assert summary.gross_profit == 320.0

    @pytest.mark.asyncio
    async def test_get_financial_records(self):
        await self.fms.record_cost("P001", 100.0, "purchase")
        await self.fms.record_revenue("P001", 200.0)

        records = await self.fms.get_financial_records(product_id="P001")
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.fms.record_cost("P001", 100.0, "purchase")
        await self.fms.record_revenue("P001", 200.0)
        stats = self.fms.get_stats()
        assert stats["total_revenue"] == 200.0
        assert stats["total_cost"] == 100.0


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_wms_crm_fms_workflow(self):
        wms = WMSManager()
        crm = CRMManager()
        fms = FMSManager()

        await wms.create_inventory(
            sku="SKU_001",
            product_name="储能电源",
            total_quantity=100,
            safety_stock=20,
        )

        await wms.stock_out("SKU_001", 10, "销售出库")

        customer = await crm.create_customer(name="张三")
        await crm.update_customer_metrics(
            customer.customer_id,
            recency_days=0,
            frequency=1,
            monetary=1000,
        )

        await fms.record_revenue("P001", 1000.0, "销售")
        await fms.record_cost("P001", 600.0, "purchase", "采购成本")

        profit = await fms.calculate_profit("P001")
        assert profit.gross_profit == 400.0

        alerts = await wms.check_alerts()
        assert len(alerts) == 0


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
