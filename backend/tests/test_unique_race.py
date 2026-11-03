"""Two saves racing on one code. The check before saving passes for both, so the
database constraint decides, and the loser must get a 409 rather than a 500."""

import pytest
from fastapi.testclient import TestClient

from app.api import depots, facilities, storage_points
from test_depots import depot_payload
from test_facilities import facility_payload
from test_storage_points import point_payload
from test_validation import auth_headers  # noqa: F401

RECORDS = {
    "depot": (
        "/api/v1/depots", depots, "_validate_depot",
        lambda code: depot_payload(code=code, is_active=False), "A depot with this code already exists.",
    ),
    "storage_point": (
        "/api/v1/storage-points", storage_points, "_validate_point_code",
        lambda code: point_payload(point_code=code),
        "A storage point with this code already exists.",
    ),
    "facility": (
        "/api/v1/facilities", facilities, "_validate_facility_code",
        lambda code: facility_payload(facility_code=code),
        "A processing facility with this code already exists.",
    ),
}


def lose_the_race(monkeypatch: pytest.MonkeyPatch, module, check: str) -> None:
    """Make the pre-save check miss the other save, as it would in a race."""
    monkeypatch.setattr(module, check, lambda *args, **kwargs: None)


@pytest.mark.parametrize("record", RECORDS)
def test_a_raced_duplicate_code_is_a_409(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch,
    record: str,
) -> None:
    path, module, check, payload, message = RECORDS[record]
    assert client.post(path, headers=auth_headers, json=payload("RACE-1")).status_code == 201
    lose_the_race(monkeypatch, module, check)

    response = client.post(path, headers=auth_headers, json=payload("RACE-1"))

    assert response.status_code == 409
    assert response.json()["detail"] == message


@pytest.mark.parametrize("record", RECORDS)
def test_a_raced_duplicate_on_update_is_a_409(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch,
    record: str,
) -> None:
    path, module, check, payload, message = RECORDS[record]
    client.post(path, headers=auth_headers, json=payload("RACE-1"))
    second = client.post(path, headers=auth_headers, json=payload("RACE-2")).json()
    lose_the_race(monkeypatch, module, check)

    response = client.put(f"{path}/{second['id']}", headers=auth_headers, json=payload("RACE-1"))

    assert response.status_code == 409
    assert response.json()["detail"] == message
    # The failed save leaves the session usable for the next request.
    assert client.get(f"{path}/{second['id']}", headers=auth_headers).status_code == 200
