"""Solar-position regression checks against the retained Jodhpur reference fixture."""

import json
from pathlib import Path

import pandas as pd
import pytest

from farm_twin.models.solar.pv_engine import solar_position


FIXTURE = Path(__file__).parent / "golden" / "pvlib_jodhpur_clearsky.json"
GOLDEN = json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("day", ["2026-03-21", "2026-06-21", "2026-12-21"])
def test_jodhpur_solar_noon_zenith_matches_reference(day: str) -> None:
    # The reference fixture records apparent solar noon zenith. Minute resolution makes
    # this comparison independent of civil-clock minute rounding in the reference tool.
    times = pd.date_range(f"{day} 00:00", f"{day} 23:59", freq="min", tz="Asia/Kolkata")
    position = solar_position(times, latitude_deg=26.2389, longitude_deg=73.0243)
    actual = float(position.zenith_deg.min())
    expected = GOLDEN[day]["noon_zenith_deg"]
    assert actual == pytest.approx(expected, abs=0.1)
