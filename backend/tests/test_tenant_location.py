"""A tenant's own attendance location: create once, read, update in place.

Without this endpoint a freshly onboarded tenant has no geofence and
check-in/out can never succeed - see `app.services.tenant.service`.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.models import AttendanceLocation, Tenant, User, UserRole
from tests.conftest import auth_header

LOCATION_PATH = "/api/v1/tenant/me/location"


def test_reading_before_any_location_exists_is_404(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    tenant = tenant_factory(slug="fresh-co")
    user_factory(tenant, email="admin@fresh-co.com", role=UserRole.TENANT_ADMIN)
    token = login("fresh-co", "admin@fresh-co.com").json()["access_token"]

    response = client.get(LOCATION_PATH, headers=auth_header(token))
    assert response.status_code == 404


def test_tenant_admin_can_create_the_location(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    tenant = tenant_factory(slug="fresh-co-2")
    user_factory(tenant, email="admin@fresh-co-2.com", role=UserRole.TENANT_ADMIN)
    token = login("fresh-co-2", "admin@fresh-co-2.com").json()["access_token"]

    response = client.post(
        LOCATION_PATH,
        json={"name": "HQ", "latitude": 12.9716, "longitude": 77.5946},
        headers=auth_header(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "HQ"
    assert body["geofence_radius_meters"] == 150  # DEFAULT_GEOFENCE_RADIUS_METERS
    assert body["description"] is None  # optional, and never supplied here

    read_back = client.get(LOCATION_PATH, headers=auth_header(token))
    assert read_back.status_code == 200
    assert read_back.json()["name"] == "HQ"


def test_creating_a_location_with_an_explicit_blank_description_succeeds(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    """Regression test: the frontend's location form always sends
    `description` (an empty string when the field is left blank), never
    omits the key - unlike `test_tenant_admin_can_create_the_location`
    above, which relies on the field's default and never actually validates
    a submitted value. An empty string reaching `trim_or_none` becomes
    `None`, and Pydantic previously tried to apply `LocationDescription`'s
    `max_length` constraint to that `None` directly, raising an unhandled
    `TypeError` (500) instead of accepting the value - see
    `app.schemas.attendance_location.LocationDescription`.
    """
    tenant = tenant_factory(slug="fresh-co-blank-desc")
    user_factory(tenant, email="admin@fresh-co-blank-desc.com", role=UserRole.TENANT_ADMIN)
    token = login("fresh-co-blank-desc", "admin@fresh-co-blank-desc.com").json()["access_token"]

    response = client.post(
        LOCATION_PATH,
        json={"name": "HQ", "description": "", "latitude": 12.9716, "longitude": 77.5946},
        headers=auth_header(token),
    )

    assert response.status_code == 201
    assert response.json()["description"] is None


def test_the_optional_description_is_stored_and_trimmed(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    tenant = tenant_factory(slug="fresh-co-8")
    user_factory(tenant, email="admin@fresh-co-8.com", role=UserRole.TENANT_ADMIN)
    token = login("fresh-co-8", "admin@fresh-co-8.com").json()["access_token"]

    response = client.post(
        LOCATION_PATH,
        json={
            "name": "HQ",
            "description": "  3rd floor, Brigade Towers  ",
            "latitude": 12.9716,
            "longitude": 77.5946,
        },
        headers=auth_header(token),
    )

    assert response.status_code == 201
    assert response.json()["description"] == "3rd floor, Brigade Towers"


def test_the_description_can_be_updated_independently_of_other_fields(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    tenant = tenant_factory(slug="fresh-co-9")
    location_factory(tenant, name="HQ")
    user_factory(tenant, email="admin@fresh-co-9.com", role=UserRole.TENANT_ADMIN)
    token = login("fresh-co-9", "admin@fresh-co-9.com").json()["access_token"]

    response = client.patch(
        LOCATION_PATH, json={"description": "Near the main gate"}, headers=auth_header(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "Near the main gate"
    assert body["name"] == "HQ"  # untouched


def test_creating_a_second_location_is_409(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    tenant = tenant_factory(slug="fresh-co-3")
    location_factory(tenant)
    user_factory(tenant, email="admin@fresh-co-3.com", role=UserRole.TENANT_ADMIN)
    token = login("fresh-co-3", "admin@fresh-co-3.com").json()["access_token"]

    response = client.post(
        LOCATION_PATH,
        json={"name": "Second Office", "latitude": 1.0, "longitude": 1.0},
        headers=auth_header(token),
    )
    assert response.status_code == 409


def test_manager_and_staff_cannot_create_a_location(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    tenant = tenant_factory(slug="fresh-co-4")
    user_factory(
        tenant, email="manager@fresh-co-4.com", employee_code="MGR-1", role=UserRole.MANAGER
    )
    user_factory(
        tenant, email="staff@fresh-co-4.com", employee_code="EMP-2", role=UserRole.STAFF
    )
    manager_token = login("fresh-co-4", "manager@fresh-co-4.com").json()["access_token"]
    staff_token = login("fresh-co-4", "staff@fresh-co-4.com").json()["access_token"]

    payload = {"name": "HQ", "latitude": 12.9716, "longitude": 77.5946}
    assert (
        client.post(LOCATION_PATH, json=payload, headers=auth_header(manager_token)).status_code
        == 403
    )
    assert (
        client.post(LOCATION_PATH, json=payload, headers=auth_header(staff_token)).status_code
        == 403
    )


def test_updating_before_any_location_exists_is_404(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    tenant = tenant_factory(slug="fresh-co-5")
    user_factory(tenant, email="admin@fresh-co-5.com", role=UserRole.TENANT_ADMIN)
    token = login("fresh-co-5", "admin@fresh-co-5.com").json()["access_token"]

    response = client.patch(
        LOCATION_PATH, json={"geofence_radius_meters": 200}, headers=auth_header(token)
    )
    assert response.status_code == 404


def test_tenant_admin_can_update_the_geofence_radius(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    tenant = tenant_factory(slug="fresh-co-6")
    location_factory(tenant, geofence_radius_meters=150)
    user_factory(tenant, email="admin@fresh-co-6.com", role=UserRole.TENANT_ADMIN)
    token = login("fresh-co-6", "admin@fresh-co-6.com").json()["access_token"]

    response = client.patch(
        LOCATION_PATH, json={"geofence_radius_meters": 300}, headers=auth_header(token)
    )
    assert response.status_code == 200
    assert response.json()["geofence_radius_meters"] == 300


def test_out_of_range_coordinates_are_rejected(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    tenant = tenant_factory(slug="fresh-co-7")
    user_factory(tenant, email="admin@fresh-co-7.com", role=UserRole.TENANT_ADMIN)
    token = login("fresh-co-7", "admin@fresh-co-7.com").json()["access_token"]

    response = client.post(
        LOCATION_PATH,
        json={"name": "HQ", "latitude": 999.0, "longitude": 77.5946},
        headers=auth_header(token),
    )
    assert response.status_code == 422


def test_cross_tenant_location_isolation(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    """Tenant A's admin must never see or affect Tenant B's location."""
    tenant_a = tenant_factory(slug="loc-a")
    tenant_b = tenant_factory(slug="loc-b")
    location_factory(tenant_b, name="B's Office")
    user_factory(tenant_a, email="admin@loc-a.com", role=UserRole.TENANT_ADMIN)
    token_a = login("loc-a", "admin@loc-a.com").json()["access_token"]

    # A has no location of its own, even though B does.
    assert client.get(LOCATION_PATH, headers=auth_header(token_a)).status_code == 404
