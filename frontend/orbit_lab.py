"""Interactive trajectory exploration tools for the OrbitX mission-control dashboard."""

from __future__ import annotations

import math
from datetime import timedelta

import plotly.graph_objects as go
import streamlit as st

from backend.formatting import format_ist
from backend.orbital_engine import build_satellite, compute_position


MEAN_EARTH_RADIUS_KM = 6371.0088


def surface_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two sub-satellite points, in kilometres."""
    values = (lat1, lon1, lat2, lon2)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Coordinates must be finite numbers.")
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90):
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not (-180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        raise ValueError("Longitude must be between -180 and 180 degrees.")

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lambda = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    # Floating-point rounding can put the value a few ulps outside [0, 1].
    haversine = min(1.0, max(0.0, haversine))
    return 2 * MEAN_EARTH_RADIUS_KM * math.asin(math.sqrt(haversine))


def render_orbit_lab(tle, position, track, illustrative: bool = False) -> None:
    """Render a time-scrubbable, explicitly model-based orbital exploration panel."""
    st.subheader("Trajectory time machine")
    st.markdown(
        "Scrub forward along the propagated orbit to inspect a future ISS position. "
        "Every point is calculated from the **same loaded TLE and SGP4 model**—this is "
        "a forecast, not a live spacecraft telemetry feed."
    )

    if track is None or track.empty or "time_utc" not in track.columns:
        st.warning("A ground track is not available for this session. Try recalculating the track.")
        return

    available_minutes = max(
        0,
        int((track["time_utc"].iloc[-1].to_pydatetime() - position.time_utc).total_seconds() // 60),
    )
    max_minutes = min(720, available_minutes)
    if max_minutes < 1:
        st.info("Increase the ground-track prediction length in Mission Controls to explore future positions.")
        return

    default_minutes = min(45, max_minutes)
    offset_minutes = st.slider(
        "Jump forward from the current calculated position",
        min_value=0,
        max_value=max_minutes,
        value=default_minutes,
        step=1,
        format="%d min",
        key="orbit_lab_offset_minutes",
        help="Select a future instant within the ground-track window. The position is propagated at that exact time.",
    )

    selected_time = position.time_utc + timedelta(minutes=offset_minutes)
    try:
        selected = compute_position(build_satellite(tle), selected_time)
    except Exception as exc:
        st.error(f"Could not propagate the selected instant: {exc}")
        return

    displacement = surface_distance_km(
        position.latitude_deg,
        position.longitude_deg,
        selected.latitude_deg,
        selected.longitude_deg,
    )
    altitude_change = selected.altitude_km - position.altitude_km

    st.caption(
        f"Selected instant: **{format_ist(selected.time_utc)}** · "
        f"Offset: **+{offset_minutes} min** · "
        + ("Illustrative sample elements are active." if illustrative else "Using the currently loaded orbital elements.")
    )

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Latitude", f"{selected.latitude_deg:+.3f}°", help="WGS-84 geodetic latitude of the sub-satellite point.")
    metric2.metric("Longitude", f"{selected.longitude_deg:+.3f}°", help="WGS-84 geodetic longitude, wrapped to ±180°.")
    metric3.metric("Altitude", f"{selected.altitude_km:.1f} km", delta=f"{altitude_change:+.1f} km", help="Height above the WGS-84 reference ellipsoid.")
    metric4.metric("Orbital speed", f"{selected.speed_km_s:.3f} km/s", help="Inertial speed relative to Earth's centre.")

    st.metric(
        "Surface displacement from current subpoint",
        f"{displacement:,.0f} km",
        help="Great-circle distance between the current and selected sub-satellite points. This is not the 3-D distance travelled by the spacecraft.",
    )

    # Show the predicted altitude history and mark the exact scrubber selection.
    chart_data = track.copy()
    chart_data["time_utc"] = chart_data["time_utc"]
    chart_data = chart_data[
        chart_data["time_utc"].apply(lambda value: value.to_pydatetime() if hasattr(value, "to_pydatetime") else value)
        <= selected_time
    ]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=chart_data["time_utc"],
            y=chart_data["altitude_km"],
            mode="lines",
            name="Predicted altitude",
            line={"color": "#38bdf8", "width": 2.5},
            hovertemplate="%{x}<br>Altitude: %{y:.2f} km<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[selected.time_utc],
            y=[selected.altitude_km],
            mode="markers",
            name="Selected instant",
            marker={"color": "#f97316", "size": 11, "line": {"color": "#ffffff", "width": 1.5}},
            hovertemplate="Selected position<br>Altitude: %{y:.2f} km<extra></extra>",
        )
    )
    fig.update_layout(
        title="Orbital altitude profile",
        xaxis_title="Time (UTC)",
        yaxis_title="Ellipsoidal altitude (km)",
        height=360,
        margin={"l": 20, "r": 20, "t": 55, "b": 25},
        paper_bgcolor="#0b1426",
        plot_bgcolor="#111c33",
        font={"color": "#d6e2f5"},
        legend={"orientation": "h", "y": 1.12, "x": 0},
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#24324f")
    fig.update_yaxes(gridcolor="#24324f")
    st.plotly_chart(fig, width="stretch")

    snapshot = (
        "time_utc,latitude_deg,longitude_deg,altitude_km,speed_km_s,offset_minutes,data_mode\n"
        f"{selected.time_utc.isoformat()},{selected.latitude_deg:.8f},"
        f"{selected.longitude_deg:.8f},{selected.altitude_km:.5f},"
        f"{selected.speed_km_s:.6f},{offset_minutes},"
        f"{'SAMPLE' if illustrative else 'CURRENT_TLE'}\n"
    )
    st.download_button(
        "⬇ Export selected position (CSV)",
        data=snapshot,
        file_name="orbitx_selected_position.csv",
        mime="text/csv",
        key="orbit_lab_export_position",
    )
    st.caption(
        "Interpretation note: the surface displacement measures movement of the ground track, "
        "not spacecraft path length. Forecast quality depends on TLE age and unmodelled events; "
        "the displayed precision is numerical formatting, not a guarantee of physical accuracy."
    )
