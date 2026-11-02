"""Only so many optimizer runs at once, and a crash never holds a slot."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import scenarios
from app.core.config import settings
from app.services.optimizer_slots import OptimizerBusy, optimizer_slot, reset_slots
from test_optimization import (  # noqa: F401
    clean_roads,
    fake_roads,
    optimize,
    saved,
)
from test_validation import auth_headers, build_scenario  # noqa: F401

BUSY = "The optimizer is busy. Try again shortly."


@pytest.fixture(autouse=True)
def fresh_slots() -> None:
    reset_slots()
    yield
    reset_slots()


@pytest.fixture
def scenario(
    client: TestClient, registered_user: dict[str, str], db_session: Session, clean_roads: None
):
    return build_scenario(db_session, registered_user["email"])


def test_a_run_past_the_limit_gets_503(
    client: TestClient, auth_headers: dict[str, str], scenario
) -> None:
    with optimizer_slot(), optimizer_slot():
        response = optimize(client, auth_headers, scenario.id)

    assert response.status_code == 503
    assert response.json()["detail"] == BUSY


def test_no_batch_is_saved_when_busy(
    client: TestClient, auth_headers: dict[str, str], scenario, db_session: Session
) -> None:
    with optimizer_slot(), optimizer_slot():
        optimize(client, auth_headers, scenario.id)

    assert saved(db_session) == []


def test_a_finished_run_frees_its_slot(
    client: TestClient, auth_headers: dict[str, str], scenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "optimizer_max_concurrent", 1)
    monkeypatch.setattr(settings, "optimizer_time_limit_s", 1)

    assert optimize(client, auth_headers, scenario.id).status_code == 200
    assert optimize(client, auth_headers, scenario.id).status_code == 200


def test_a_crashed_run_frees_its_slot(
    client: TestClient, auth_headers: dict[str, str], scenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "optimizer_max_concurrent", 1)
    monkeypatch.setattr(settings, "optimizer_time_limit_s", 1)
    real = scenarios.optimize_scenario

    def explode(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(scenarios, "optimize_scenario", explode)
    assert optimize(client, auth_headers, scenario.id).status_code == 500

    monkeypatch.setattr(scenarios, "optimize_scenario", real)
    assert optimize(client, auth_headers, scenario.id).status_code == 200


def test_the_limit_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "optimizer_max_concurrent", 1)

    with optimizer_slot():
        with pytest.raises(OptimizerBusy):
            with optimizer_slot():
                pass


def test_the_default_limit_is_two() -> None:
    assert type(settings).model_fields["optimizer_max_concurrent"].default == 2
