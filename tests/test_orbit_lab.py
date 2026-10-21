"""Unit tests for geometry helpers used by the interactive orbit lab."""

from __future__ import annotations

import pytest

from frontend.orbit_lab import surface_distance_km


def test_surface_distance_is_zero_for_identical_points():
    assert surface_distance_km(17.0, 83.0, 17.0, 83.0) == pytest.approx(0.0)


def test_surface_distance_for_one_degree_at_equator():
    assert surface_distance_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.195, abs=0.01)


def test_surface_distance_handles_antimeridian_short_path():
    assert surface_distance_km(0.0, 179.5, 0.0, -179.5) == pytest.approx(111.195, abs=0.01)


@pytest.mark.parametrize(
    "coords",
    [
        (91.0, 0.0, 0.0, 0.0),
        (0.0, 181.0, 0.0, 0.0),
        (0.0, 0.0, float("nan"), 0.0),
    ],
)
def test_surface_distance_rejects_invalid_coordinates(coords):
    with pytest.raises(ValueError):
        surface_distance_km(*coords)
