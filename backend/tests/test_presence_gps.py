"""GPS validation, distance calculation and geofencing (spec checks 1-12)."""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest

from app.core.config import Settings
from app.models import AttendanceLocation, Tenant
from app.services.presence.gps import (
    EARTH_RADIUS_METERS,
    haversine_distance_meters,
    is_valid_accuracy,
    is_valid_latitude,
    is_valid_longitude,
    verify_gps,
)
from app.services.presence.results import FailureReason
from tests.conftest import (
    METERS_PER_DEGREE_LATITUDE,
    OFFICE_LATITUDE,
    OFFICE_LONGITUDE,
    offset_north,
)


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "environment": "test",
        "jwt_secret_key": "a-sufficiently-long-test-secret-key-1234",
        "max_gps_accuracy_meters": 100.0,
        "qr_challenge_ttl_seconds": 30,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[arg-type]


@pytest.fixture
def config() -> Settings:
    return make_settings()


# ---------------------------------------------------------------------------
# 1-4. Coordinate and accuracy validation
# ---------------------------------------------------------------------------


def test_valid_coordinates_accepted() -> None:
    for latitude in (-90.0, -45.5, 0.0, 12.9716, 90.0):
        assert is_valid_latitude(latitude), latitude
    for longitude in (-180.0, -77.0, 0.0, 77.5946, 180.0):
        assert is_valid_longitude(longitude), longitude
    for accuracy in (0.0, 1.5, 12.5, 5000.0):
        assert is_valid_accuracy(accuracy), accuracy


def test_invalid_latitude_rejected() -> None:
    for latitude in (-90.001, 90.001, 91.0, -1000.0, float("nan"), float("inf")):
        assert not is_valid_latitude(latitude), latitude


def test_invalid_longitude_rejected() -> None:
    for longitude in (-180.001, 180.001, 360.0, float("nan"), float("-inf")):
        assert not is_valid_longitude(longitude), longitude


def test_invalid_accuracy_rejected() -> None:
    for accuracy in (-0.1, -1.0, -999.0, float("nan")):
        assert not is_valid_accuracy(accuracy), accuracy


def test_invalid_input_is_rejected_not_clamped(
    config: Settings,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    """Out-of-range coordinates must fail, never be silently pulled into range."""
    location = location_factory(tenant_factory(slug="acme"))

    result = verify_gps(
        latitude=95.0,  # impossible
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=5.0,
        location=location,
        config=config,
    )

    assert result.verified is False
    assert result.reason is FailureReason.GPS_INVALID
    # No distance is invented from an invalid coordinate.
    assert result.distance_meters is None


# ---------------------------------------------------------------------------
# 11. Distance correctness
# ---------------------------------------------------------------------------


def test_distance_is_zero_for_the_same_point() -> None:
    assert haversine_distance_meters(
        OFFICE_LATITUDE, OFFICE_LONGITUDE, OFFICE_LATITUDE, OFFICE_LONGITUDE
    ) == pytest.approx(0.0, abs=1e-6)


def test_one_degree_of_latitude_is_about_111_km() -> None:
    """A degree along a meridian is R*radians(1) exactly under this model."""
    distance = haversine_distance_meters(0.0, 0.0, 1.0, 0.0)

    assert distance == pytest.approx(METERS_PER_DEGREE_LATITUDE, abs=1.0)
    assert distance == pytest.approx(EARTH_RADIUS_METERS * math.radians(1), abs=1e-6)


def test_longitude_distance_shrinks_with_latitude() -> None:
    """The check a naive Euclidean implementation cannot pass.

    A degree of longitude spans ~111 km at the equator but only ~55.6 km at 60
    degrees north (a cos(latitude) factor). Treating degrees as a flat grid would
    return the same number for both and silently distort every geofence away
    from the equator.
    """
    at_equator = haversine_distance_meters(0.0, 0.0, 0.0, 1.0)
    at_sixty = haversine_distance_meters(60.0, 0.0, 60.0, 1.0)

    assert at_equator == pytest.approx(METERS_PER_DEGREE_LATITUDE, abs=1.0)
    assert at_sixty == pytest.approx(at_equator * math.cos(math.radians(60.0)), rel=1e-3)
    assert at_sixty < at_equator / 1.9


def test_distance_is_symmetric_and_monotonic() -> None:
    near = offset_north(OFFICE_LATITUDE, 100.0)
    far = offset_north(OFFICE_LATITUDE, 1000.0)

    d_near = haversine_distance_meters(near, OFFICE_LONGITUDE, OFFICE_LATITUDE, OFFICE_LONGITUDE)
    d_far = haversine_distance_meters(far, OFFICE_LONGITUDE, OFFICE_LATITUDE, OFFICE_LONGITUDE)

    assert d_near < d_far
    assert d_near == pytest.approx(100.0, abs=0.5)
    assert d_far == pytest.approx(1000.0, abs=2.0)
    # Symmetry.
    assert haversine_distance_meters(
        OFFICE_LATITUDE, OFFICE_LONGITUDE, near, OFFICE_LONGITUDE
    ) == pytest.approx(d_near, abs=1e-9)


def test_antipodal_distance_is_half_the_circumference() -> None:
    """Exercises the clamp that stops floating-point error breaking asin()."""
    distance = haversine_distance_meters(0.0, 0.0, 0.0, 180.0)

    assert distance == pytest.approx(math.pi * EARTH_RADIUS_METERS, rel=1e-9)
    assert not math.isnan(distance)


# ---------------------------------------------------------------------------
# 5-7, 12. Geofence evaluation
# ---------------------------------------------------------------------------


def test_inside_geofence_succeeds(
    config: Settings,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    """The specification's own example: 73 m inside a 150 m radius."""
    location = location_factory(tenant_factory(slug="acme"))

    result = verify_gps(
        latitude=offset_north(OFFICE_LATITUDE, 73.0),
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=12.5,
        location=location,
        config=config,
    )

    assert result.verified is True
    assert result.reason is None
    assert result.distance_meters == pytest.approx(73.0, abs=1.0)
    assert result.accuracy_meters == 12.5


def test_outside_geofence_fails(
    config: Settings,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    """The specification's counter-example: 240 m outside a 150 m radius."""
    location = location_factory(tenant_factory(slug="acme"))

    result = verify_gps(
        latitude=offset_north(OFFICE_LATITUDE, 240.0),
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=12.5,
        location=location,
        config=config,
    )

    assert result.verified is False
    assert result.reason is FailureReason.OUTSIDE_GEOFENCE
    # The distance is still reported, so a rejection is diagnosable.
    assert result.distance_meters == pytest.approx(240.0, abs=2.0)


def test_geofence_boundary_is_inclusive(
    config: Settings,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    """`distance <= radius` counts as inside, per the specification."""
    location = location_factory(tenant_factory(slug="acme"), geofence_radius_meters=150)

    just_inside = verify_gps(
        latitude=offset_north(OFFICE_LATITUDE, 149.0),
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=5.0,
        location=location,
        config=config,
    )
    just_outside = verify_gps(
        latitude=offset_north(OFFICE_LATITUDE, 151.0),
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=5.0,
        location=location,
        config=config,
    )

    assert just_inside.verified is True
    assert just_outside.verified is False


def test_geofence_radius_comes_from_the_location_row(
    config: Settings,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    """The same coordinates must flip verdict when the tenant's radius changes."""
    acme = tenant_factory(slug="acme")
    beta = tenant_factory(slug="beta")
    tight = location_factory(acme, geofence_radius_meters=50)
    wide = location_factory(beta, geofence_radius_meters=500)

    latitude = offset_north(OFFICE_LATITUDE, 200.0)

    tight_result = verify_gps(
        latitude=latitude,
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=5.0,
        location=tight,
        config=config,
    )
    wide_result = verify_gps(
        latitude=latitude,
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=5.0,
        location=wide,
        config=config,
    )

    assert tight_result.verified is False
    assert wide_result.verified is True
    # 150 is nowhere in the decision - only the stored radii were consulted.
    assert tight.geofence_radius_meters == 50
    assert wide.geofence_radius_meters == 500


def test_result_carries_server_calculated_values(
    config: Settings,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    location = location_factory(tenant_factory(slug="acme"))

    result = verify_gps(
        latitude=offset_north(OFFICE_LATITUDE, 40.0),
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=9.25,
        location=location,
        config=config,
    )

    assert result.distance_meters is not None
    assert result.distance_meters > 0
    assert result.accuracy_meters == 9.25
    # verify_gps takes no distance parameter at all, so a client-supplied
    # distance has no way in.
    assert "distance" not in verify_gps.__code__.co_varnames[
        : verify_gps.__code__.co_argcount + verify_gps.__code__.co_kwonlyargcount
    ]


# ---------------------------------------------------------------------------
# 9. Accuracy threshold
# ---------------------------------------------------------------------------


def test_poor_accuracy_fails_even_when_inside_the_geofence(
    config: Settings,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    """A vague reading cannot evidence presence, however good its centre looks."""
    location = location_factory(tenant_factory(slug="acme"))

    result = verify_gps(
        latitude=OFFICE_LATITUDE,  # dead centre
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=250.0,  # but "somewhere within 250 m"
        location=location,
        config=config,
    )

    assert result.verified is False
    assert result.reason is FailureReason.GPS_ACCURACY_TOO_LOW
    assert result.distance_meters == pytest.approx(0.0, abs=1e-6)


def test_accuracy_threshold_is_configurable(
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    """The same reading flips verdict with MAX_GPS_ACCURACY_METERS."""
    location = location_factory(tenant_factory(slug="acme"))
    kwargs = {
        "latitude": OFFICE_LATITUDE,
        "longitude": OFFICE_LONGITUDE,
        "accuracy_meters": 80.0,
        "location": location,
    }

    strict = verify_gps(**kwargs, config=make_settings(max_gps_accuracy_meters=50.0))
    lenient = verify_gps(**kwargs, config=make_settings(max_gps_accuracy_meters=100.0))

    assert strict.verified is False
    assert strict.reason is FailureReason.GPS_ACCURACY_TOO_LOW
    assert lenient.verified is True


def test_accuracy_exactly_at_the_threshold_is_accepted() -> None:
    """The bound is `accuracy > max` fails, so equality passes."""
    from app.models.attendance_location import AttendanceLocation as Location

    location = Location(
        tenant_id=None,  # type: ignore[arg-type]  # not persisted
        name="probe",
        latitude=OFFICE_LATITUDE,
        longitude=OFFICE_LONGITUDE,
        geofence_radius_meters=150,
    )

    result = verify_gps(
        latitude=OFFICE_LATITUDE,
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=100.0,
        location=location,
        config=make_settings(max_gps_accuracy_meters=100.0),
    )

    assert result.verified is True


def test_zero_accuracy_is_valid(
    config: Settings,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    location = location_factory(tenant_factory(slug="acme"))

    result = verify_gps(
        latitude=OFFICE_LATITUDE,
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=0.0,
        location=location,
        config=config,
    )

    assert result.verified is True
