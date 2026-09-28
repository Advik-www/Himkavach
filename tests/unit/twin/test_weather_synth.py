"""Tests for the synthetic fallback weather generator."""

from datetime import UTC, datetime

import numpy as np
from himkavach_twin.weather_synth import generate_synthetic_weather


class TestSyntheticWeather:
    """Physical and determinism tests for synthetic weather generation."""

    def _make_weather(self, seed: int = 42, hours: int = 24, **kwargs):
        rng = np.random.default_rng(seed)
        start = datetime(2026, 6, 21, 0, 0, tzinfo=UTC)
        return generate_synthetic_weather(
            latitude=kwargs.get("latitude", -70.77),
            longitude=kwargs.get("longitude", 11.73),
            start=start,
            hours=hours,
            rng=rng,
            **{k: v for k, v in kwargs.items() if k not in ("latitude", "longitude")},
        )

    def test_output_count_matches_hours(self):
        obs = self._make_weather(hours=48)
        assert len(obs) == 48

    def test_temperatures_physically_plausible(self):
        obs = self._make_weather(hours=168)  # 1 week
        temps = [o.temperature_c for o in obs]
        assert all(-60.0 < t < 20.0 for t in temps), (
            f"Implausible temp range: {min(temps)} to {max(temps)}"
        )

    def test_wind_speeds_non_negative(self):
        obs = self._make_weather(hours=168)
        winds = [o.wind_speed_m_s for o in obs]
        assert all(w >= 0.0 for w in winds)

    def test_pressure_physically_plausible(self):
        obs = self._make_weather(hours=168)
        pressures = [o.surface_pressure_hpa for o in obs]
        assert all(900.0 < p < 1060.0 for p in pressures), (
            f"Implausible pressure: {min(pressures)} to {max(pressures)}"
        )

    def test_irradiance_zero_during_polar_night(self):
        """In June at -70.77°S, the sun is well below the horizon (polar night)."""
        obs = self._make_weather(hours=48, latitude=-70.77)
        ghis = [o.ghi_w_m2 for o in obs]
        # During polar night, almost all hours should have zero GHI
        zero_count = sum(1 for g in ghis if g == 0.0)
        assert zero_count >= 45, (
            f"Expected ~all zero GHI during polar night, got {zero_count}/48 zeros"
        )

    def test_humidity_bounded(self):
        obs = self._make_weather(hours=168)
        rhs = [o.relative_humidity_pct for o in obs]
        assert all(20.0 <= r <= 100.0 for r in rhs)

    def test_determinism_same_seed(self):
        """Same seed must produce identical output."""
        obs1 = self._make_weather(seed=123, hours=72)
        obs2 = self._make_weather(seed=123, hours=72)
        for o1, o2 in zip(obs1, obs2, strict=True):
            assert o1.temperature_c == o2.temperature_c
            assert o1.wind_speed_m_s == o2.wind_speed_m_s
            assert o1.ghi_w_m2 == o2.ghi_w_m2

    def test_determinism_different_seed(self):
        """Different seeds produce different output."""
        obs1 = self._make_weather(seed=123, hours=72)
        obs2 = self._make_weather(seed=456, hours=72)
        temps1 = [o.temperature_c for o in obs1]
        temps2 = [o.temperature_c for o in obs2]
        assert temps1 != temps2

    def test_timestamps_sequential(self):
        obs = self._make_weather(hours=48)
        for i in range(1, len(obs)):
            diff = (obs[i].timestamp - obs[i - 1].timestamp).total_seconds()
            assert diff == 3600.0, f"Non-hourly gap at step {i}: {diff}s"

    def test_pressure_tendency_uses_lookback(self):
        """Pressure tendency should be nonzero after first 3 hours."""
        obs = self._make_weather(hours=24)
        # First 3 observations have tendency 0 (no lookback)
        for o in obs[:3]:
            assert o.pressure_tendency_3h_hpa == 0.0
        # Later observations should have some nonzero tendencies
        later_tendencies = [o.pressure_tendency_3h_hpa for o in obs[3:]]
        assert any(t != 0.0 for t in later_tendencies)
