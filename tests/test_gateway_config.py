from pathlib import Path

from src.services.gateway_governance_service import GatewayGovernanceService


def test_gateway_governance_service_exposes_environment_and_rollback():
    service = GatewayGovernanceService()
    data = service.get_status()
    assert data["environment_targets"]["local"]["status"] == "ready"
    assert data["environment_targets"]["prod"]["environment_connected"] is False
    assert "preprod" in data["environment_targets"]
    assert data["environment_targets"]["preprod"]["environment_connected"] is False
    assert data["rollback_strategy"]["policy"] == "config-first rollback"
    assert "kong-routes.yml" in data["validation"]["checksums"]
    assert "runtime_probe" in data
    assert "delivery_pack" in data
    assert data["runtime_probe"]["smoke_test_passed"] is False
    assert data["business_proxy_runtime"]["route_binding_count"] == 3
    assert data["business_proxy_runtime"]["desired_upstream_ports"] == [8000]
    assert data["business_proxy_runtime"]["local_bundle_ready"] is True
    assert "route_probes" in data["business_proxy_runtime"]["runtime_probe"]
    assert data["traffic_governance"]["gateway_rate_limits"][0]["limit"]["unit"] == "minute"
    assert data["traffic_governance"]["tenant_dimension"]["explicit_tenant_required"] is True
    assert data["authentication_runtime"]["gateway_layer"]["plugin_enabled"] is True
    assert data["authentication_runtime"]["upstream_layer"]["mode"] == "oauth2-jwt"
    assert data["authentication_runtime"]["local_acceptance_ready"] is True
    assert data["canary_release"]["local_acceptance_ready"] is True
    assert data["logging_aggregation"]["local_acceptance_ready"] is True


def test_gateway_split_files_exist():
    gateway_dir = Path("k8s/gateway")
    assert (gateway_dir / "kong.yml").exists()
    assert (gateway_dir / "kong-services.yml").exists()
    assert (gateway_dir / "kong-routes.yml").exists()
    assert (gateway_dir / "kong-plugins.yml").exists()
    assert (gateway_dir / "kong-consumers.yml").exists()


def test_gateway_services_use_host_backend_service():
    services_text = Path("k8s/gateway/kong-services.yml").read_text(encoding="utf-8")

    assert "url: http://host.docker.internal:18000" in services_text
    assert "url: http://app:8000" not in services_text
