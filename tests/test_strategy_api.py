from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import app
from app.strategy_loader import strategy_loader


CLIENT = TestClient(app)
TEST_STRATEGY_ID = "api_test_signal_strategy"


VALID_CODE = '''
STRATEGY_META = {
    "strategy_id": "user_supplied_id",
    "strategy_type": "event_strategy",
    "research_only": False,
}


def required_features(params):
    return ["close"]


def prepare_features(df, params):
    return df


def generate_signals(df, params):
    threshold = float(params.get("threshold", 0.0))
    return [{"signal": 1 if float(row.get("close", 0.0)) > threshold else 0} for row in df]
'''


def cleanup_strategy(strategy_id: str = TEST_STRATEGY_ID) -> None:
    path = Path("strategies/gawain") / f"{strategy_id}.py"
    path.unlink(missing_ok=True)
    strategy_loader.discover()


def payload(strategy_id: str = TEST_STRATEGY_ID) -> dict:
    return {
        "strategy_id": strategy_id,
        "name": "API Test Signal Strategy",
        "description": "Created through the executable strategy management API.",
        "version": "0.1.0",
        "parameter_schema": {"threshold": {"type": "float", "min": 0.0, "max": 10.0}},
        "default_parameters": {"threshold": 1.0},
        "code": VALID_CODE,
    }


def test_create_get_validate_patch_delete_strategy_lifecycle():
    cleanup_strategy()
    try:
        created = CLIENT.post("/strategies", json=payload())
        assert created.status_code == 200
        created_body = created.json()
        assert created_body["strategy_id"] == TEST_STRATEGY_ID
        assert created_body["research_only"] is True
        assert created_body["strategy_type"] == "signal_strategy"
        assert created_body["parameter_schema"]["threshold"]["type"] == "float"

        path = Path("strategies/gawain") / f"{TEST_STRATEGY_ID}.py"
        assert path.exists()
        source = path.read_text(encoding="utf-8")
        assert "# <shark_bay_managed_meta>" in source
        assert "'research_only': True" in source
        assert "'strategy_type': 'signal_strategy'" in source

        fetched = CLIENT.get(f"/strategies/{TEST_STRATEGY_ID}")
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "API Test Signal Strategy"

        listed = CLIENT.get("/strategies")
        assert listed.status_code == 200
        assert TEST_STRATEGY_ID in listed.json()["strategies"]

        valid = CLIENT.post(f"/strategies/{TEST_STRATEGY_ID}/validate", json={"parameters": {"threshold": 2.0}})
        assert valid.status_code == 200
        assert valid.json()["valid"] is True
        assert valid.json()["resolved_parameters"]["threshold"] == 2.0

        invalid = CLIENT.post(f"/strategies/{TEST_STRATEGY_ID}/validate", json={"parameters": {"threshold": 99.0}})
        assert invalid.status_code == 400
        assert invalid.json()["valid"] is False
        assert "above maximum" in invalid.json()["errors"][0]

        patched = CLIENT.patch(
            f"/strategies/{TEST_STRATEGY_ID}",
            json={"description": "Updated metadata only.", "default_parameters": {"threshold": 3.0}},
        )
        assert patched.status_code == 200
        assert patched.json()["description"] == "Updated metadata only."
        assert patched.json()["default_parameters"]["threshold"] == 3.0
        assert patched.json()["research_only"] is True
        assert patched.json()["strategy_type"] == "signal_strategy"

        deleted = CLIENT.delete(f"/strategies/{TEST_STRATEGY_ID}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] == TEST_STRATEGY_ID
        assert not path.exists()
    finally:
        cleanup_strategy()


def test_create_strategy_rejects_invalid_id_and_missing_contract():
    cleanup_strategy("Invalid-ID")
    bad_id = CLIENT.post("/strategies", json=payload("Invalid-ID"))
    assert bad_id.status_code == 400
    assert "strategy_id must match" in bad_id.json()["detail"]["message"]

    missing_contract_payload = payload("missing_contract_strategy")
    missing_contract_payload["code"] = 'STRATEGY_META = {"strategy_id": "missing_contract_strategy"}\n'
    try:
        bad_contract = CLIENT.post("/strategies", json=missing_contract_payload)
        assert bad_contract.status_code == 400
        assert "required_features" in bad_contract.json()["detail"]["message"]
    finally:
        cleanup_strategy("missing_contract_strategy")


def test_builtin_strategy_cannot_be_deleted_or_patched():
    deleted = CLIENT.delete("/strategies/sma_crossover")
    assert deleted.status_code == 403
    assert "Builtin strategies cannot be deleted" in deleted.json()["detail"]["message"]

    patched = CLIENT.patch("/strategies/sma_crossover", json={"description": "nope"})
    assert patched.status_code == 403


def test_reload_strategies_returns_registry():
    reloaded = CLIENT.post("/strategies/reload")
    assert reloaded.status_code == 200
    assert "strategies" in reloaded.json()
    assert "sma_crossover" in reloaded.json()["strategies"]


def test_static_strategy_routes_are_registered_before_dynamic_routes():
    paths = [route.path for route in app.routes]
    dynamic_index = paths.index("/strategies/{strategy_id}")
    assert paths.index("/strategies/reload") < dynamic_index
    assert paths.index("/strategies/registry") < dynamic_index


def test_post_strategies_validation_errors_are_json():
    cleanup_strategy("bad_json_error_strategy")
    bad_payload = payload("bad_json_error_strategy")
    bad_payload["code"] = "def not_a_strategy():\n    return None\n"
    response = CLIENT.post("/strategies", json=bad_payload)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "ValueError"
    assert "STRATEGY_META" in detail["message"]
