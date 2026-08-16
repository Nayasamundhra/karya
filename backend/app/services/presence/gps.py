"""GPS evidence validation, distance calculation and geofence evaluation.

Everything in this module is pure computation over values the server already
holds: the device-reported coordinates and the tenant's stored attendance
location. No client-supplied distance or "verified" flag is ever read.

**Limitation, stated plainly:** GPS is an *evidence signal*, not proof of
physical presence. Coordinates can be manipulated on a rooted or developer-mode
device, and this module cannot detect that. It is one of two independent signals
precisely because neither is sufficient alone - the dynamic QR requires the
person to be in front of a display that rotates every few seconds. Device
attestation, which would raise the cost of spoofing, is deliberately out of
scope for this phase.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Final

from app.core.config import Settings, settings
from app.models.attendance_location import AttendanceLocation
from app.services.presence.results import FailureReason, GPSResult

#: Mean Earth radius in metres (IUGG). The Earth is an oblate spheroid, so a
#: spherical model carries up to ~0.5% error; at geofence scale (tens to
#: hundreds of metres) that is well under a metre and far below consumer GPS
#: accuracy, so it is not the limiting factor here.
EARTH_RADIUS_METERS: Final[float] = 6_371_008.8

MIN_LATITUDE: Final[float] = -90.0
MAX_LATITUDE: Final[float] = 90.0
MIN_LONGITUDE: Final[float] = -180.0
MAX_LONGITUDE: Final[float] = 180.0


def is_valid_latitude(latitude: float) -> bool:
    """Whether ``latitude`` is a real number within [-90, +90]."""
    # A NaN comparison is always False, so NaN and infinities fail here.
    return MIN_LATITUDE <= latitude <= MAX_LATITUDE


def is_valid_longitude(longitude: float) -> bool:
    """Whether ``longitude`` is a real number within [-180, +180]."""
    return MIN_LONGITUDE <= longitude <= MAX_LONGITUDE


def is_valid_accuracy(accuracy_meters: float) -> bool:
    """Whether ``accuracy_meters`` is a real, non-negative number."""
    return accuracy_meters >= 0.0


def haversine_distance_meters(
    latitude_1: float, longitude_1: float, latitude_2: float, longitude_2: float
) -> float:
    """Great-circle distance between two points, in metres.

    Uses the haversine formula. A naive Euclidean distance over raw
    latitude/longitude would be wrong in two ways: degrees are not metres, and a
    degree of longitude shrinks with ``cos(latitude)`` - roughly 111 km at the
    equator but only 55 km at 60 degrees. Getting that wrong would silently
    widen or narrow every geofence away from the equator.
    """
    phi_1, phi_2 = radians(latitude_1), radians(latitude_2)
    delta_phi = phi_2 - phi_1
    delta_lambda = radians(longitude_2 - longitude_1)

    h = (
        sin(delta_phi / 2) ** 2
        + cos(phi_1) * cos(phi_2) * sin(delta_lambda / 2) ** 2
    )
    # Clamp: floating-point error can push h a hair above 1 for antipodal
    # points, which would make asin() raise.
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(min(1.0, h)))


def verify_gps(
    *,
    latitude: float,
    longitude: float,
    accuracy_meters: float,
    location: AttendanceLocation,
    config: Settings | None = None,
) -> GPSResult:
    """Evaluate device-reported GPS evidence against a tenant's geofence.

    Checks, in order:

    1. the coordinates and accuracy are well-formed,
    2. the reported accuracy is no worse than ``MAX_GPS_ACCURACY_METERS``, and
    3. the server-computed distance is within the location's own
       ``geofence_radius_meters``.

    The radius comes from the ``AttendanceLocation`` row, never from a constant
    here, so a tenant can widen or tighten its own geofence.

    The distance is returned even when verification fails, which is what makes a
    rejection diagnosable ("you were 420 m away") instead of merely "no".
    """
    config = config or settings

    if not (
        is_valid_latitude(latitude)
        and is_valid_longitude(longitude)
        and is_valid_accuracy(accuracy_meters)
    ):
        # Invalid input is rejected outright, never clamped into range: silently
        # "correcting" a bad coordinate would fabricate evidence.
        return GPSResult(
            verified=False,
            distance_meters=None,
            accuracy_meters=accuracy_meters,
            reason=FailureReason.GPS_INVALID,
        )

    distance_meters = haversine_distance_meters(
        latitude, longitude, location.latitude, location.longitude
    )

    if accuracy_meters > config.max_gps_accuracy_meters:
        # A reading this vague cannot evidence presence inside the geofence even
        # if its centre happens to fall within it.
        return GPSResult(
            verified=False,
            distance_meters=distance_meters,
            accuracy_meters=accuracy_meters,
            reason=FailureReason.GPS_ACCURACY_TOO_LOW,
        )

    if distance_meters > location.geofence_radius_meters:
        return GPSResult(
            verified=False,
            distance_meters=distance_meters,
            accuracy_meters=accuracy_meters,
            reason=FailureReason.OUTSIDE_GEOFENCE,
        )

    return GPSResult(
        verified=True,
        distance_meters=distance_meters,
        accuracy_meters=accuracy_meters,
    )
