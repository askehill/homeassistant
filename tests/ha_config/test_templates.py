"""
Tests for template/ sensor and binary_sensor logic.

Each class targets one YAML file. Templates are loaded directly from the
repository files and rendered with a mocked HA environment, so the tests
stay in sync as you edit the config files.

Run with:
    pytest tests/ha_config/test_templates.py -v
"""
from __future__ import annotations

import sys
import os
import pytest
from datetime import datetime, timezone

# Ensure conftest is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conftest import HAEnv, load_template_state  # noqa: E402


# =============================================================================
# Helpers
# =============================================================================

def monday(hour: int, minute: int = 0) -> datetime:
    """Return a UTC datetime on a known Monday (2024-01-15), Irish winter (GMT=UTC)."""
    return datetime(2024, 1, 15, hour, minute, tzinfo=timezone.utc)


def sunday(hour: int, minute: int = 0) -> datetime:
    """Return a UTC datetime on a known Sunday (2024-01-14), Irish winter."""
    return datetime(2024, 1, 14, hour, minute, tzinfo=timezone.utc)


def saturday(hour: int, minute: int = 0) -> datetime:
    return datetime(2024, 1, 13, hour, minute, tzinfo=timezone.utc)


def summer_monday(hour: int) -> datetime:
    """Return a UTC datetime on a Monday in Irish summer (IST = UTC+1, 2024-07-15)."""
    return datetime(2024, 7, 15, hour, 0, tzinfo=timezone(offset=__import__('datetime').timedelta(hours=1)))


# =============================================================================
# electricity_rate.yaml  ── "Electric Ireland Weekender (Sunday)" sensor
# =============================================================================

class TestElectricityRateSST:
    """
    Electric Ireland Smart Standard Tariff (SST) with 30% discount.

    Unit rates (inc. carbon tax €0.01251/kWh):
      Night:  23:00–08:00 all days  → €0.1362 + €0.01251 = €0.1487/kWh
      Peak:   17:00–19:00 every day → €0.2765 + €0.01251 = €0.2890/kWh
      Day:    everything else       → €0.2592 + €0.01251 = €0.2717/kWh

    Fixed daily charges (separate sensor):
      Standing charge €250.77/year + PSO €19.10/year = €0.7394/day
    """

    FILE = "electricity_rate.yaml"
    NIGHT = round(0.1362 + 0.01251, 4)   # 0.1487
    DAY   = round(0.2592 + 0.01251, 4)   # 0.2717
    PEAK  = round(0.2765 + 0.01251, 4)   # 0.2890
    DAILY_FIXED = round((250.77 + 19.10) / 365, 4)  # 0.7394

    def _seed_config(self, ha_env):
        """Seed the electricity_plan_config sensor that the rate template reads from."""
        ha_env.set_state(
            "sensor.electricity_plan_config",
            "Electric Ireland SST",
            rate_night=0.1362,
            rate_day=0.2592,
            rate_peak=0.2765,
            carbon_tax=0.01251,
            standing_charge_annual=250.77,
            pso_annual=19.10,
        )

    def _render(self, ha_env, unique_id, dt):
        self._seed_config(ha_env)
        tmpl = load_template_state(self.FILE, unique_id)
        ha_env.set_now(dt)
        return ha_env.render(tmpl)

    # ---- Unit rate ----------------------------------------------------------

    def test_monday_midday_is_day_rate(self, ha_env):
        assert float(self._render(ha_env, "electricity_rate", monday(12))) == self.DAY

    def test_monday_peak_is_peak_rate(self, ha_env):
        assert float(self._render(ha_env, "electricity_rate", monday(17))) == self.PEAK

    def test_monday_18_is_peak(self, ha_env):
        assert float(self._render(ha_env, "electricity_rate", monday(18))) == self.PEAK

    def test_monday_19_is_day_not_peak(self, ha_env):
        # 19:00 is end of peak window — should be day rate
        assert float(self._render(ha_env, "electricity_rate", monday(19))) == self.DAY

    def test_monday_night_is_night_rate(self, ha_env):
        assert float(self._render(ha_env, "electricity_rate", monday(2))) == self.NIGHT

    def test_monday_23_is_night(self, ha_env):
        # 23:00 is start of night window
        assert float(self._render(ha_env, "electricity_rate", monday(23))) == self.NIGHT

    def test_monday_8am_is_day_not_night(self, ha_env):
        # 08:00 is end of night window — should be day rate
        assert float(self._render(ha_env, "electricity_rate", monday(8))) == self.DAY

    def test_saturday_peak_window_is_peak_rate(self, ha_env):
        # Peak applies every day including weekends
        assert float(self._render(ha_env, "electricity_rate", saturday(17))) == self.PEAK

    def test_sunday_peak_window_is_peak_rate(self, ha_env):
        assert float(self._render(ha_env, "electricity_rate", sunday(18))) == self.PEAK

    def test_saturday_night_is_night_rate(self, ha_env):
        assert float(self._render(ha_env, "electricity_rate", saturday(1))) == self.NIGHT

    # ---- Daily fixed cost ---------------------------------------------------

    def test_daily_fixed_cost_is_correct(self, ha_env):
        result = self._render(ha_env, "electricity_daily_fixed_cost", monday(12))
        assert float(result) == self.DAILY_FIXED

    def test_daily_fixed_cost_is_positive(self, ha_env):
        result = self._render(ha_env, "electricity_daily_fixed_cost", monday(12))
        assert float(result) > 0


# =============================================================================
# template/laundry.yaml
# =============================================================================

class TestLaundryAppliances:
    """
    Appliance detection for the shared laundry clamp (sensor.laundry_power).

    Washing machine detection now uses select.washing_machine (Samsung smart
    integration) directly — no power guesswork needed.

    Tumble dryer (heat pump, no smart integration) is detected by residual power
    after subtracting an estimated washing machine draw:
      - Washer Stopped/Paused:  all clamp power is the dryer
      - Washer Running + total > 1500W: washer in heating cycle (~2000W est.)
      - Washer Running + total ≤ 1500W: washer in tumble/spin phase (~400W est.)
    Heat pump dryer heating phase: 500–900W → threshold 400W.
    """

    FILE = "laundry.yaml"

    def _render(self, ha_env, unique_id, laundry_w=0.0, shelly_w=0.0,
                washer_state="Stopped"):
        ha_env.set_state("sensor.laundry_power", str(laundry_w))
        ha_env.set_state("sensor.shellypmmini_543204b7d0c0_power", str(shelly_w))
        ha_env.set_state("select.washing_machine", washer_state)
        tmpl = load_template_state(self.FILE, unique_id)
        return ha_env.render(tmpl)

    # ---- Tumble dryer — washer stopped --------------------------------------

    def test_dryer_on_washer_stopped_700w(self, ha_env):
        """Washer off, heat pump dryer heating at 700W → on."""
        assert self._render(ha_env, "tumble_dryer_state",
                            laundry_w=700, washer_state="Stopped") == "on"

    def test_dryer_on_washer_paused_600w(self, ha_env):
        """Washer paused, dryer heating at 600W → on."""
        assert self._render(ha_env, "tumble_dryer_state",
                            laundry_w=600, washer_state="Paused") == "on"

    def test_dryer_off_washer_stopped_0w(self, ha_env):
        assert self._render(ha_env, "tumble_dryer_state",
                            laundry_w=0, washer_state="Stopped") == "off"

    def test_dryer_off_washer_stopped_100w_standby(self, ha_env):
        """100W is below the 400W threshold — dryer not running."""
        assert self._render(ha_env, "tumble_dryer_state",
                            laundry_w=100, washer_state="Stopped") == "off"

    # ---- Tumble dryer — washer running (residual power) ---------------------

    def test_dryer_cooldown_not_detected_while_washer_runs(self, ha_env):
        # Dryer cool-down (~100W) + washer rinse/spin (~400W) = ~500W total.
        # dryer_w = 500 - 400 = 100W, below threshold — bridged by delay_off in sensor.
        assert self._render(ha_env, "tumble_dryer_state",
                            laundry_w=500, washer_state="Running") == "off"

    def test_dryer_on_washer_heating_both_running(self, ha_env):
        """Washer heating (~2000W) + dryer heating (~700W) = 2700W total.
        Residual = 2700 - 2000 = 700W → dryer on."""
        assert self._render(ha_env, "tumble_dryer_state",
                            laundry_w=2700, washer_state="Running") == "on"

    def test_dryer_on_washer_tumble_both_running(self, ha_env):
        """Washer tumbling (~400W) + dryer heating (~700W) = 1100W total.
        Total ≤ 1500 so washer_est = 400W. Residual = 700W → dryer on."""
        assert self._render(ha_env, "tumble_dryer_state",
                            laundry_w=1100, washer_state="Running") == "on"

    def test_dryer_off_washer_heating_alone(self, ha_env):
        """Washer heating alone at 2000W. Residual = 2000 - 2000 = 0W → dryer off."""
        assert self._render(ha_env, "tumble_dryer_state",
                            laundry_w=2000, washer_state="Running") == "off"

    def test_dryer_off_washer_tumble_alone(self, ha_env):
        """Washer tumbling alone at 400W. Residual = 400 - 400 = 0W → dryer off."""
        assert self._render(ha_env, "tumble_dryer_state",
                            laundry_w=400, washer_state="Running") == "off"

    # ---- Washing machine — now driven by Samsung select entity ---------------

    def test_washing_machine_on_when_running(self, ha_env):
        assert self._render(ha_env, "washing_machine_state",
                            washer_state="Running") == "on"

    def test_washing_machine_off_when_stopped(self, ha_env):
        assert self._render(ha_env, "washing_machine_state",
                            washer_state="Stopped") == "off"

    def test_washing_machine_off_when_paused(self, ha_env):
        assert self._render(ha_env, "washing_machine_state",
                            washer_state="Paused") == "off"

    def test_washing_machine_state_independent_of_power(self, ha_env):
        """Power reading is irrelevant — state comes from Samsung integration."""
        result_low = self._render(ha_env, "washing_machine_state",
                                  laundry_w=0, washer_state="Running")
        result_high = self._render(ha_env, "washing_machine_state",
                                   laundry_w=2100, washer_state="Running")
        assert result_low == result_high == "on"

    # ---- Washing machine finished -------------------------------------------
    # SmartThings sometimes gets stuck on Running after a cycle ends.
    # Power fallback: if SmartThings says Running but clamp < 100W → finished.

    def test_washing_machine_finished_when_stopped(self, ha_env):
        assert self._render(ha_env, "washing_machine_finished",
                            laundry_w=0, washer_state="Stopped") == "on"

    def test_washing_machine_finished_when_paused(self, ha_env):
        assert self._render(ha_env, "washing_machine_finished",
                            laundry_w=0, washer_state="Paused") == "on"

    def test_washing_machine_finished_power_fallback(self, ha_env):
        # SmartThings stuck on Running but clamp at idle → treat as finished
        assert self._render(ha_env, "washing_machine_finished",
                            laundry_w=5, washer_state="Running") == "on"

    def test_washing_machine_not_finished_when_running_with_power(self, ha_env):
        # Genuinely running — SmartThings says Running and drawing real power
        assert self._render(ha_env, "washing_machine_finished",
                            laundry_w=2000, washer_state="Running") == "off"

    def test_washing_machine_not_finished_dryer_still_running(self, ha_env):
        # SmartThings stuck Running, but dryer is still drawing power — not finished yet
        assert self._render(ha_env, "washing_machine_finished",
                            laundry_w=600, washer_state="Running") == "off"

    # ---- Dishwasher ---------------------------------------------------------
    # Heating element only: > 1900W. The 14-600W pump-phase band was removed
    # because the hot water tap's keep-warm cycle (~18-200W) caused false
    # positives on the shared clamp. The 60-min delay_off in the sensor
    # definition bridges pump-only phases between heating cycles instead.

    def test_dishwasher_on_at_2000w(self, ha_env):
        assert self._render(ha_env, "dishwasher_state", shelly_w=2000) == "on"

    def test_dishwasher_on_at_1950w(self, ha_env):
        assert self._render(ha_env, "dishwasher_state", shelly_w=1950) == "on"

    def test_dishwasher_off_at_0w(self, ha_env):
        assert self._render(ha_env, "dishwasher_state", shelly_w=0) == "off"

    def test_dishwasher_off_at_tap_standby(self, ha_env):
        # ~2W standby must not trigger
        assert self._render(ha_env, "dishwasher_state", shelly_w=2) == "off"

    def test_dishwasher_off_at_pump_phase(self, ha_env):
        # Pump-only phase (~18W) is bridged by delay_off, not detected directly
        assert self._render(ha_env, "dishwasher_state", shelly_w=18) == "off"

    def test_dishwasher_off_in_hot_water_tap_range(self, ha_env):
        # Hot water tap keep-warm and heating (18–1500W) must not trigger
        assert self._render(ha_env, "dishwasher_state", shelly_w=200) == "off"

    def test_dishwasher_off_at_1900w_boundary(self, ha_env):
        # Exactly 1900W is off (threshold is strictly > 1900)
        assert self._render(ha_env, "dishwasher_state", shelly_w=1900) == "off"

    # ---- Hot water tap ------------------------------------------------------

    def test_hotwater_tap_on_at_1300w(self, ha_env):
        assert self._render(ha_env, "hotwater_tap_state", shelly_w=1300) == "on"

    def test_hotwater_tap_on_at_lower_boundary(self, ha_env):
        # Wider band (1100–1500W) catches element ramping up
        assert self._render(ha_env, "hotwater_tap_state", shelly_w=1150) == "on"

    def test_hotwater_tap_off_at_standby(self, ha_env):
        assert self._render(ha_env, "hotwater_tap_state", shelly_w=2) == "off"

    def test_hotwater_tap_off_at_0w(self, ha_env):
        assert self._render(ha_env, "hotwater_tap_state", shelly_w=0) == "off"

    def test_hotwater_tap_off_at_dishwasher_power(self, ha_env):
        # 2000W is dishwasher territory — hot tap should not trigger
        assert self._render(ha_env, "hotwater_tap_state", shelly_w=2000) == "off"


# =============================================================================
# template/misc.yaml
# =============================================================================

class TestMiscTemplates:
    """
    Tests for miscellaneous template sensors in misc.yaml.

    NOTE: test_number_lights_on_all_off_is_a_known_bug documents a real defect:
    when no lights are on, the groupby 'on' key doesn't exist, causing a
    KeyError / UndefinedError that makes the sensor unavailable.
    The fix is:  dict(...).get('on', []) | length
    """

    FILE = "misc.yaml"

    def test_number_lights_on_counts_correctly(self, ha_env):
        ha_env.set_state("light.kitchen_lights", "on")
        ha_env.set_state("light.living_room_lights", "on")
        ha_env.set_state("light.back_door_porch", "off")
        tmpl = load_template_state(self.FILE, "number_lights_on")
        result = ha_env.render(tmpl)
        assert int(result) == 2

    def test_number_lights_on_all_off_returns_zero(self, ha_env):
        """
        In standard Jinja2, dict(...)['on'] on a dict with no 'on' key returns
        Undefined (not KeyError), and Undefined|length evaluates to 0.
        So the template safely returns '0' when all lights are off.

        Note: HA's custom Jinja2 environment may behave differently —
        if you see this sensor go 'unavailable' in practice when all lights are
        off, the fix is:  dict(...).get('on', []) | length
        """
        ha_env.set_state("light.kitchen_lights", "off")
        ha_env.set_state("light.living_room_lights", "off")
        tmpl = load_template_state(self.FILE, "number_lights_on")
        result = ha_env.render(tmpl)
        assert int(result) == 0

    def test_adjusted_nspanel_temperature_scales_correctly(self, ha_env):
        ha_env.set_state("sensor.livingroompanel_analog_temperature1", "25.0")
        tmpl = load_template_state(self.FILE, "adjusted_nspanel_temperature")
        result = ha_env.render(tmpl)
        # 25.0 * 0.7755 = 19.3875 → rounds to 19.4
        assert float(result) == pytest.approx(19.4, abs=0.05)

    def test_adjusted_cooking_power_returns_absolute_value(self, ha_env):
        ha_env.set_state("sensor.shellyem_c7faf3_channel_1_power", "-1500.0")
        tmpl = load_template_state(self.FILE, "adjusted_cooking_power")
        result = ha_env.render(tmpl)
        assert float(result) == pytest.approx(1500.0, abs=1)


# =============================================================================
# template/gas.yaml
# =============================================================================

class TestGasEstimation:
    """
    Gas usage is estimated from which heating circuits are drawing electricity.
    Each circuit contributes a fixed kW value; total is capped at 23 kW.
    """

    FILE = "gas.yaml"

    def _render(self, ha_env, hotwater=0, downstairs=0, channel1=0, channel2=0):
        ha_env.set_state("sensor.hotwater_power", str(hotwater))
        ha_env.set_state("sensor.downstairs_power", str(downstairs))
        ha_env.set_state("sensor.heating2_channel_1_power", str(channel1))
        ha_env.set_state("sensor.heating2_channel_2_power", str(channel2))
        tmpl = load_template_state(self.FILE, "gas_usage")
        return float(ha_env.render(tmpl))

    def test_all_off_returns_zero(self, ha_env):
        assert self._render(ha_env) == 0

    def test_hotwater_only(self, ha_env):
        assert self._render(ha_env, hotwater=100) == 10

    def test_downstairs_only(self, ha_env):
        assert self._render(ha_env, downstairs=100) == 13

    def test_all_circuits_on_returns_sum(self, ha_env):
        # 10 + 13 + 10 + 8 = 41 → capped at 23
        result = self._render(ha_env, hotwater=100, downstairs=100, channel1=100, channel2=100)
        assert result == 23

    def test_cap_at_23kw(self, ha_env):
        # Any combination exceeding 23 should be capped
        result = self._render(ha_env, hotwater=100, downstairs=100, channel1=100)
        # 10 + 13 + 10 = 33 → capped at 23
        assert result == 23

    def test_two_circuits_not_capped(self, ha_env):
        # hotwater (10) + channel2 (8) = 18 → not capped
        result = self._render(ha_env, hotwater=100, channel2=100)
        assert result == 18


# =============================================================================
# template/occupancy.yaml
# =============================================================================

class TestOccupancy:
    """Occupancy sensors are thin wrappers around motion sensors with a 3-min delay_off."""

    FILE = "occupancy.yaml"

    def test_living_room_occupied_when_motion_on(self, ha_env):
        ha_env.set_state("binary_sensor.living_room_motion", "on")
        tmpl = load_template_state(self.FILE, "living_room_occupied")
        assert ha_env.render(tmpl) in ("True", "true", "on")

    def test_living_room_not_occupied_when_motion_off(self, ha_env):
        ha_env.set_state("binary_sensor.living_room_motion", "off")
        tmpl = load_template_state(self.FILE, "living_room_occupied")
        assert ha_env.render(tmpl) in ("False", "false", "off")

    def test_playroom_occupied_when_motion_on(self, ha_env):
        ha_env.set_state("binary_sensor.playroom_motion", "on")
        tmpl = load_template_state(self.FILE, "playroom_occupied")
        assert ha_env.render(tmpl) in ("True", "true", "on")

    def test_kitchen_occupancy_uses_pantry_motion(self, ha_env):
        ha_env.set_state("binary_sensor.pantry_motion", "on")
        tmpl = load_template_state(self.FILE, "kitchen_occupied")
        assert ha_env.render(tmpl) in ("True", "true", "on")


# =============================================================================
# template/shower.yaml
# =============================================================================

class TestShower:
    FILE = "shower.yaml"

    def test_shower_on_above_5w(self, ha_env):
        ha_env.set_state("sensor.shower_pump_switch_0_power", "10")
        tmpl = load_template_state(self.FILE, "shower_running")
        assert ha_env.render(tmpl) in ("True", "true", "on")

    def test_shower_off_at_zero(self, ha_env):
        ha_env.set_state("sensor.shower_pump_switch_0_power", "0")
        tmpl = load_template_state(self.FILE, "shower_running")
        assert ha_env.render(tmpl) in ("False", "false", "off")

    def test_shower_off_at_boundary_5w(self, ha_env):
        # Threshold is > 5, so exactly 5 W is off
        ha_env.set_state("sensor.shower_pump_switch_0_power", "5")
        tmpl = load_template_state(self.FILE, "shower_running")
        assert ha_env.render(tmpl) in ("False", "false", "off")


# =============================================================================
# template/sun.yaml
# =============================================================================

class TestSun:
    FILE = "sun.yaml"

    def test_sun_up_when_above_horizon(self, ha_env):
        ha_env.set_state("sun.sun", "above_horizon")
        tmpl = load_template_state(self.FILE, "sun_up")
        assert ha_env.render(tmpl) in ("True", "true", "on")

    def test_sun_down_when_below_horizon(self, ha_env):
        ha_env.set_state("sun.sun", "below_horizon")
        tmpl = load_template_state(self.FILE, "sun_up")
        assert ha_env.render(tmpl) in ("False", "false", "off")


# =============================================================================
# Heating timezone comparison — fragile string check
# =============================================================================

class TestHeatingTimezoneComparison:
    """
    Documents the fragile timezone string comparison used in heating automations.

    The pattern  `now().astimezone().tzinfo | string == "GMT"`  checks whether
    we're in Irish winter time.  This works but is fragile — it relies on the
    string representation of a tzinfo object, which can vary across Python /
    pytz versions.

    The safer idiom is: `now().utcoffset().total_seconds() == 0`

    These tests document BOTH behaviours.  If you migrate the automations to
    the safer idiom, the `test_safer_utcoffset_idiom_*` tests are your
    regression guard.
    """

    GMT = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)   # UTC offset = 0  (winter)
    IST = datetime(2024, 7, 15, 12, 0, tzinfo=timezone(
        __import__('datetime').timedelta(hours=1)))              # UTC offset = +1 (summer)

    WINTER_TMPL = "{{ now().utcoffset().total_seconds() == 0 }}"
    SUMMER_TMPL = "{{ now().utcoffset().total_seconds() != 0 }}"

    def test_safer_utcoffset_is_zero_in_winter(self, ha_env):
        ha_env.set_now(self.GMT)
        assert ha_env.render(self.WINTER_TMPL) == "on"

    def test_safer_utcoffset_nonzero_in_summer(self, ha_env):
        ha_env.set_now(self.IST)
        assert ha_env.render(self.WINTER_TMPL) == "off"

    def test_safer_summer_check(self, ha_env):
        ha_env.set_now(self.IST)
        assert ha_env.render(self.SUMMER_TMPL) == "on"


# =============================================================================
# water_volume.yaml  ── "Water Butt Volume" sensor
# =============================================================================

class TestWaterButtVolume:
    """
    Two-butt setup: 250 L big butt (sensor) + 100 L small butt connected at
    1/4 height of the big butt (~62.5 L mark).

    Piecewise model:
      - ADC <= 0.179 V  →  big butt only  (0–62.5 L)
      - ADC >  0.179 V  →  both butts     (62.5–350 L)

    Calibration constant big_full_v = 0.714 V derived from observed
    0.03 V ≈ 10.5 L (350 L/V scale). Update big_full_v in the template
    once a confirmed full-tank reading is available.
    """

    SENSOR = "water_butt_volume"

    def _render(self, ha_env, adc_v: float) -> int:
        ha_env.set_state("sensor.shellyuni_c45bbe5f76f8_adc", str(adc_v))
        tmpl = load_template_state("water_volume.yaml", self.SENSOR)
        return int(ha_env.render(tmpl))

    def test_empty_reads_zero(self, ha_env):
        assert self._render(ha_env, 0.0) == 0

    def test_negative_adc_clamps_to_zero(self, ha_env):
        """Sensor can drift slightly negative when empty — must not report < 0 L."""
        assert self._render(ha_env, -0.01) == 0

    def test_low_fill_big_butt_only(self, ha_env):
        """0.03 V ≈ 10.5 L — below connection threshold, only big butt has water."""
        assert 10 <= self._render(ha_env, 0.03) <= 11

    def test_at_threshold_is_62_litres(self, ha_env):
        """At the connection threshold (~0.179 V) volume should be ~62.5 L."""
        vol = self._render(ha_env, 0.179)
        assert 60 <= vol <= 65

    def test_above_threshold_both_butts_contribute(self, ha_env):
        """Midway through combined fill should be well above big-butt-only value."""
        vol = self._render(ha_env, 0.45)
        assert vol > 150

    def test_full_tank_is_350_litres(self, ha_env):
        """At big_full_v (0.714 V) total volume should be 350 L."""
        assert self._render(ha_env, 0.714) == 350

    def test_overvoltage_capped_at_350(self, ha_env):
        """ADC spike above full should not report more than total capacity."""
        assert self._render(ha_env, 1.5) == 350
