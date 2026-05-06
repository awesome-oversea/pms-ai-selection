from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "k8s" / "gateway"
REQUIRED_FILES = [
    "kong.yml",
    "kong-services.yml",
    "kong-routes.yml",
    "kong-plugins.yml",
    "kong-consumers.yml",
]
REQUIRED_TOKENS = {
    "kong.yml": ["_format_version", "services:", "consumers:"],
    "kong-services.yml": ["pms-internal-service", "pms-bff-service", "pms-openapi-service", "http://host.docker.internal:18000"],
    "kong-routes.yml": ["pms-internal-route", "pms-bff-route", "pms-openapi-route"],
    "kong-plugins.yml": ["key-auth", "rate-limiting", "X-Gateway-Layer:bff"],
    "kong-consumers.yml": ["bff-client", "bff-demo-key"],
}


def validate() -> tuple[bool, list[str], dict[str, str]]:
    errors: list[str] = []
    checksums: dict[str, str] = {}
    for name in REQUIRED_FILES:
        path = GATEWAY_DIR / name
        if not path.exists():
            errors.append(f"missing:{name}")
            continue
        content = path.read_text(encoding="utf-8")
        checksums[name] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        for token in REQUIRED_TOKENS.get(name, []):
            if token not in content:
                errors.append(f"token_missing:{name}:{token}")
    return len(errors) == 0, errors, checksums


def main() -> int:
    ok, errors, checksums = validate()
    print("gateway_files=", ",".join(REQUIRED_FILES))
    for name, value in checksums.items():
        print(f"checksum:{name}={value}")
    if not ok:
        print("validation_errors=")
        for item in errors:
            print(item)
        return 1
    print("gateway_config_validation=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
