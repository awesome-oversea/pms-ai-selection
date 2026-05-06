"""D66-D70 单元测试: SCM供应链 + OMS订单管理"""


import pytest
from src.infrastructure.scm_oms import (
    API1688Mock,
    OMSManager,
    OrderStatus,
    PriceLevel,
    PurchaseOrder,
    SCMManager,
    Supplier,
    SupplierLevel,
)


class TestSupplier:
    """测试供应商"""

    def test_supplier_creation(self):
        supplier = Supplier(
            supplier_id="SUP_001",
            name="测试供应商",
            moq=50,
            lead_time_days=7,
        )
        assert supplier.supplier_id == "SUP_001"
        assert supplier.moq == 50

    def test_calculate_level_gold(self):
        supplier = Supplier(
            supplier_id="SUP_001",
            name="优质供应商",
            quality_score=0.9,
            on_time_rate=0.95,
            total_orders=200,
        )
        level = supplier.calculate_level()
        assert level == SupplierLevel.GOLD

    def test_calculate_level_silver(self):
        supplier = Supplier(
            supplier_id="SUP_002",
            name="良好供应商",
            quality_score=0.7,
            on_time_rate=0.8,
            total_orders=50,
        )
        level = supplier.calculate_level()
        assert level == SupplierLevel.SILVER

    def test_supplier_to_dict(self):
        supplier = Supplier(
            supplier_id="SUP_001",
            name="测试",
            price_level=PriceLevel.LOW,
        )
        d = supplier.to_dict()
        assert d["supplier_id"] == "SUP_001"
        assert d["price_level"] == "low"


class TestPurchaseOrder:
    """测试采购订单"""

    def test_order_creation(self):
        order = PurchaseOrder(
            order_id="PO_001",
            supplier_id="SUP_001",
            product_name="储能电源",
            sku="SKU_001",
            quantity=100,
            unit_price=50.0,
            total_amount=5000.0,
        )
        assert order.order_id == "PO_001"
        assert order.status == OrderStatus.PENDING_PAYMENT

    def test_order_to_dict(self):
        order = PurchaseOrder(
            order_id="PO_001",
            supplier_id="SUP_001",
            product_name="储能电源",
            sku="SKU_001",
            quantity=100,
            unit_price=50.0,
            total_amount=5000.0,
        )
        d = order.to_dict()
        assert d["order_id"] == "PO_001"
        assert d["status"] == "pending_payment"


class TestAPI1688Mock:
    """测试1688 API模拟(D67)"""

    def setup_method(self):
        self.api = API1688Mock()

    def test_initialization(self):
        assert len(self.api._products) == 10
        assert len(self.api._suppliers) == 5

    @pytest.mark.asyncio
    async def test_product_search(self):
        result = await self.api.product_search("储能")
        assert result["success"] is True
        assert result["total"] >= 0

    @pytest.mark.asyncio
    async def test_supplier_info(self):
        result = await self.api.supplier_info("SUP_1000")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_supplier_info_not_found(self):
        result = await self.api.supplier_info("UNKNOWN")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_order_create(self):
        result = await self.api.order_create({
            "supplier_id": "SUP_1000",
            "products": [{"sku": "SKU_001", "quantity": 10}],
        })
        assert result["success"] is True
        assert "order_id" in result

    @pytest.mark.asyncio
    async def test_order_status(self):
        result = await self.api.order_status("PO_001")
        assert result["success"] is True


class TestSCMManager:
    """测试SCM管理器(D66-D68)"""

    def setup_method(self):
        self.scm = SCMManager()

    @pytest.mark.asyncio
    async def test_create_supplier(self):
        supplier = await self.scm.create_supplier(
            name="测试供应商A",
            contact_person="张三",
            moq=100,
            lead_time_days=5,
        )
        assert supplier.supplier_id.startswith("SUP_")
        assert supplier.name == "测试供应商A"

    @pytest.mark.asyncio
    async def test_get_supplier(self):
        created = await self.scm.create_supplier(name="供应商B")
        supplier = await self.scm.get_supplier(created.supplier_id)
        assert supplier.name == "供应商B"

    @pytest.mark.asyncio
    async def test_list_suppliers(self):
        await self.scm.create_supplier(name="供应商A", categories=["储能"])
        await self.scm.create_supplier(name="供应商B", categories=["耳机"])
        suppliers = await self.scm.list_suppliers(category="储能")
        assert len(suppliers) == 1

    @pytest.mark.asyncio
    async def test_update_supplier_score(self):
        supplier = await self.scm.create_supplier(name="供应商A")
        supplier.total_orders = 200
        updated = await self.scm.update_supplier_score(
            supplier.supplier_id,
            quality_score=0.9,
            on_time_rate=0.95,
        )
        assert updated.quality_score == 0.9
        assert updated.level == SupplierLevel.GOLD

    @pytest.mark.asyncio
    async def test_create_purchase_order(self):
        supplier = await self.scm.create_supplier(name="供应商A")
        order = await self.scm.create_purchase_order(
            supplier_id=supplier.supplier_id,
            product_name="储能电源",
            sku="SKU_001",
            quantity=50,
            unit_price=100.0,
        )
        assert order.order_id.startswith("PO_")
        assert order.total_amount == 5000.0

    @pytest.mark.asyncio
    async def test_get_order(self):
        supplier = await self.scm.create_supplier(name="供应商A")
        created = await self.scm.create_purchase_order(
            supplier_id=supplier.supplier_id,
            product_name="储能电源",
            sku="SKU_001",
            quantity=10,
            unit_price=50.0,
        )
        order = await self.scm.get_order(created.order_id)
        assert order.product_name == "储能电源"

    @pytest.mark.asyncio
    async def test_list_orders(self):
        supplier = await self.scm.create_supplier(name="供应商A")
        await self.scm.create_purchase_order(
            supplier_id=supplier.supplier_id,
            product_name="产品A",
            sku="SKU_001",
            quantity=10,
            unit_price=50.0,
        )
        orders = await self.scm.list_orders()
        assert len(orders) == 1

    @pytest.mark.asyncio
    async def test_search_products(self):
        result = await self.scm.search_products("储能")
        assert "products" in result

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.scm.create_supplier(name="供应商A")
        stats = self.scm.get_stats()
        assert stats["suppliers_count"] == 1


class TestOMSManager:
    """测试OMS管理器(D69)"""

    def setup_method(self):
        self.oms = OMSManager()

    def _create_test_order(self):
        order = PurchaseOrder(
            order_id="PO_001",
            supplier_id="SUP_001",
            product_name="储能电源",
            sku="SKU_001",
            quantity=10,
            unit_price=100.0,
            total_amount=1000.0,
        )
        self.oms.register_order(order)
        return order

    def test_register_order(self):
        self._create_test_order()
        assert "PO_001" in self.oms._orders

    @pytest.mark.asyncio
    async def test_update_status_pending_to_paid(self):
        self._create_test_order()
        order = await self.oms.update_order_status(
            "PO_001",
            OrderStatus.PAID,
            "付款成功",
        )
        assert order.status == OrderStatus.PAID
        assert order.paid_at is not None

    @pytest.mark.asyncio
    async def test_update_status_invalid_transition(self):
        self._create_test_order()
        order = await self.oms.update_order_status(
            "PO_001",
            OrderStatus.DELIVERED,
        )
        assert order is None

    @pytest.mark.asyncio
    async def test_update_status_to_shipped(self):
        self._create_test_order()
        await self.oms.update_order_status("PO_001", OrderStatus.PAID)
        order = await self.oms.update_order_status("PO_001", OrderStatus.SHIPPED)
        assert order.status == OrderStatus.SHIPPED
        assert order.tracking_number is not None

    @pytest.mark.asyncio
    async def test_get_tracking(self):
        self._create_test_order()
        await self.oms.update_order_status("PO_001", OrderStatus.PAID)
        await self.oms.update_order_status("PO_001", OrderStatus.SHIPPED)
        track = await self.oms.get_tracking("PO_001")
        assert track is not None
        assert track.tracking_number.startswith("SF")

    @pytest.mark.asyncio
    async def test_get_status_history(self):
        self._create_test_order()
        await self.oms.update_order_status("PO_001", OrderStatus.PAID)
        history = await self.oms.get_status_history("PO_001")
        assert len(history) == 2

    def test_get_stats(self):
        self._create_test_order()
        stats = self.oms.get_stats()
        assert stats["total_orders"] == 1


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_scm_oms_workflow(self):
        scm = SCMManager()
        oms = OMSManager()

        supplier = await scm.create_supplier(
            name="优质供应商",
            moq=50,
            lead_time_days=3,
        )

        order = await scm.create_purchase_order(
            supplier_id=supplier.supplier_id,
            product_name="户外储能电源",
            sku="SKU_001",
            quantity=100,
            unit_price=80.0,
        )

        oms.register_order(order)

        await oms.update_order_status(order.order_id, OrderStatus.PAID)
        await oms.update_order_status(order.order_id, OrderStatus.SHIPPED)

        updated = await scm.get_order(order.order_id)
        assert updated.status == OrderStatus.SHIPPED

        track = await oms.get_tracking(order.order_id)
        assert track is not None


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
