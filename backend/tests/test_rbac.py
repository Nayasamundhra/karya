"""Role-based authorization foundation (spec checks 40-46).

`require_roles` is exercised through a throwaway probe app rather than a real
route, because Phase 2 has no role-gated business endpoints yet - only the
reusable dependency that later phases will attach to theirs.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models import Tenant, User, UserRole
from tests.conftest import auth_header, make_get_db_override

ROUTES = {
    UserRole.STAFF: "/staff-only",
    UserRole.MANAGER: "/manager-only",
    UserRole.TENANT_ADMIN: "/admin-only",
    UserRole.SUPER_ADMIN: "/platform-only",
}


@pytest.fixture
def probe_client(db_session: Session) -> Callable[[], TestClient]:
    """A tiny app with one route guarded per role, plus a multi-role route."""
    probe = FastAPI()

    @probe.get("/staff-only")
    def staff_only(user: User = Depends(require_roles(UserRole.STAFF))) -> dict:
        return {"role": user.role}

    @probe.get("/manager-only")
    def manager_only(user: User = Depends(require_roles(UserRole.MANAGER))) -> dict:
        return {"role": user.role}

    @probe.get("/admin-only")
    def admin_only(
        user: User = Depends(require_roles(UserRole.TENANT_ADMIN)),
    ) -> dict:
        return {"role": user.role}

    @probe.get("/platform-only")
    def platform_only(
        user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
    ) -> dict:
        return {"role": user.role}

    @probe.get("/management")
    def management(
        user: User = Depends(
            require_roles(UserRole.TENANT_ADMIN, UserRole.MANAGER)
        ),
    ) -> dict:
        return {"role": user.role}

    probe.dependency_overrides[get_db] = make_get_db_override(db_session)

    def _make() -> TestClient:
        return TestClient(probe)

    return _make


@pytest.fixture
def token_for(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> Callable[[UserRole], str]:
    """Issue a genuine access token for a user holding ``role``."""
    tenant = tenant_factory(slug="acme")
    counter = {"n": 0}

    def _token(role: UserRole) -> str:
        counter["n"] += 1
        email = f"user{counter['n']}@acme.com"
        user_factory(
            tenant,
            email=email,
            employee_code=f"EMP-{counter['n']:03d}",
            role=role,
        )
        response = login("acme", email)
        assert response.status_code == 200
        return response.json()["access_token"]

    return _token


# ---------------------------------------------------------------------------
# 40-45. Exact-match role checks (no hierarchy)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "allowed_route"),
    [
        (UserRole.STAFF, "/staff-only"),
        (UserRole.MANAGER, "/manager-only"),
        (UserRole.TENANT_ADMIN, "/admin-only"),
        (UserRole.SUPER_ADMIN, "/platform-only"),
    ],
)
def test_role_satisfies_its_own_requirement(
    probe_client: Callable[[], TestClient],
    token_for: Callable[[UserRole], str],
    role: UserRole,
    allowed_route: str,
) -> None:
    token = token_for(role)

    with probe_client() as client:
        response = client.get(allowed_route, headers=auth_header(token))

    assert response.status_code == 200
    assert response.json()["role"] == role.value


@pytest.mark.parametrize(
    ("role", "forbidden_routes"),
    [
        (UserRole.STAFF, ["/manager-only", "/admin-only", "/platform-only"]),
        (UserRole.MANAGER, ["/staff-only", "/admin-only", "/platform-only"]),
        (UserRole.TENANT_ADMIN, ["/staff-only", "/manager-only", "/platform-only"]),
    ],
)
def test_role_does_not_satisfy_other_requirements(
    probe_client: Callable[[], TestClient],
    token_for: Callable[[UserRole], str],
    role: UserRole,
    forbidden_routes: list[str],
) -> None:
    """Roles are an exact set match: neither seniority nor STAFF is inherited."""
    token = token_for(role)

    with probe_client() as client:
        for route in forbidden_routes:
            response = client.get(route, headers=auth_header(token))
            assert response.status_code == 403, route
            assert response.json()["detail"] == "Insufficient permissions"
            # The refusal names no role, so it leaks no policy detail.
            assert role.value not in response.text


def test_super_admin_is_not_implicitly_granted_tenant_routes(
    probe_client: Callable[[], TestClient],
    token_for: Callable[[UserRole], str],
) -> None:
    """SUPER_ADMIN must be listed explicitly; it is not a wildcard."""
    token = token_for(UserRole.SUPER_ADMIN)

    with probe_client() as client:
        assert client.get("/admin-only", headers=auth_header(token)).status_code == 403
        assert (
            client.get("/platform-only", headers=auth_header(token)).status_code == 200
        )


def test_require_roles_accepts_any_of_several_roles(
    probe_client: Callable[[], TestClient],
    token_for: Callable[[UserRole], str],
) -> None:
    admin_token = token_for(UserRole.TENANT_ADMIN)
    manager_token = token_for(UserRole.MANAGER)
    staff_token = token_for(UserRole.STAFF)

    with probe_client() as client:
        assert client.get("/management", headers=auth_header(admin_token)).status_code == 200
        assert client.get("/management", headers=auth_header(manager_token)).status_code == 200
        assert client.get("/management", headers=auth_header(staff_token)).status_code == 403


def test_role_gated_routes_still_require_authentication(
    probe_client: Callable[[], TestClient],
) -> None:
    """Unauthenticated is 401, not 403 - the two are distinct outcomes."""
    with probe_client() as client:
        for route in ROUTES.values():
            response = client.get(route)
            assert response.status_code == 401, route


def test_require_roles_rejects_an_empty_role_list() -> None:
    """A dependency that permits nobody is a bug; fail at import time."""
    with pytest.raises(ValueError):
        require_roles()


# ---------------------------------------------------------------------------
# 46. No self-escalation
# ---------------------------------------------------------------------------


def test_no_endpoint_exists_for_changing_a_role() -> None:
    """Phase 2 must expose no role-management surface at all."""
    from app.main import app

    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]

    # Kept as an exact set so a future phase cannot add a user-mutation route
    # without this test noticing. Phase 3 added the two presence endpoints.
    assert set(paths) == {
        "/health",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/presence/qr/challenge",
        "/api/v1/presence/verify",
        "/api/v1/attendance/check-in",
        "/api/v1/attendance/check-out",
        "/api/v1/attendance/me",
        "/api/v1/attendance/me/history",
        "/api/v1/attendance/team/today",
        "/api/v1/attendance/users/{user_id}",
        "/api/v1/attendance/users/{user_id}/history",
    }
    for path, operations in paths.items():
        for method in operations:
            assert method.lower() in {"get", "post"}, (path, method)
        # No mutating verbs that could alter a user record.
        assert "put" not in operations
        assert "patch" not in operations
        assert "delete" not in operations


def test_role_claimed_in_a_token_cannot_override_the_database(
    db_session: Session,
    probe_client: Callable[[], TestClient],
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """Authorization reads the DB role, so a stale token cannot elevate."""
    tenant = tenant_factory(slug="acme")
    user = user_factory(tenant, email="rahul@acme.com", role=UserRole.TENANT_ADMIN)
    token = login("acme", "rahul@acme.com").json()["access_token"]

    with probe_client() as client:
        assert client.get("/admin-only", headers=auth_header(token)).status_code == 200

        # Demote in the database; the token still claims TENANT_ADMIN.
        user.role = UserRole.STAFF.value
        db_session.flush()

        assert client.get("/admin-only", headers=auth_header(token)).status_code == 403
        assert client.get("/staff-only", headers=auth_header(token)).status_code == 200


def test_me_reflects_role_but_offers_no_way_to_set_it(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """/auth/me is read-only; a role in the request must not be honoured."""
    from app.main import app

    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com", role=UserRole.STAFF)
    token = login("acme", "rahul@acme.com").json()["access_token"]

    with TestClient(app) as client:
        # A write attempt is not even routed.
        assert client.patch(
            "/api/v1/auth/me",
            json={"role": "SUPER_ADMIN"},
            headers=auth_header(token),
        ).status_code == 405
        assert client.put(
            "/api/v1/auth/me",
            json={"role": "SUPER_ADMIN"},
            headers=auth_header(token),
        ).status_code == 405
