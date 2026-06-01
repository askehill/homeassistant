"""
Shared fixtures for HA config tests.

Provides a minimal Jinja2 environment (HAEnv) that mimics Home Assistant's
template engine, with mockable states, now(), and domain-level state access.
All three test modules import from here via pytest's automatic conftest discovery.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import pytest
from jinja2 import Environment

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

HA_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATE_DIR = os.path.join(HA_ROOT, "template")
MQTT_DIR = os.path.join(HA_ROOT, "mqtt")
PACKAGES_DIR = os.path.join(HA_ROOT, "packages")


# ---------------------------------------------------------------------------
# State mock
# ---------------------------------------------------------------------------

class MockState:
    """Mimics a single HA state object (hass.states.get(...))."""

    def __init__(self, entity_id: str, state: str, attributes: dict | None = None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}


class StatesProxy:
    """
    Dual-use object that acts as both:
      - a callable:   states('sensor.foo')  -> str
      - a namespace:  states.light          -> list[MockState] for the light domain

    This matches how HA exposes `states` inside Jinja2 templates.
    """

    def __init__(self, store: dict[str, MockState]):
        self._store = store

    def __call__(self, entity_id: str) -> str:
        obj = self._store.get(entity_id)
        return obj.state if obj else "unknown"

    def __getattr__(self, domain: str) -> list[MockState]:
        if domain.startswith("_"):
            raise AttributeError(domain)
        return [s for eid, s in self._store.items() if eid.split(".")[0] == domain]


# ---------------------------------------------------------------------------
# HA Jinja2 environment
# ---------------------------------------------------------------------------

class HAEnv:
    """
    Minimal HA-compatible Jinja2 environment with mockable state and clock.

    Typical usage::

        env = HAEnv()
        env.set_now(datetime(2024, 1, 7, 14, 0))          # Sunday 14:00
        env.set_state("sensor.laundry_power", "520")
        result = env.render("{{ states('sensor.laundry_power') | float }}")
        assert result == "520.0"
    """

    def __init__(self) -> None:
        self._store: dict[str, MockState] = {}
        # Default: Monday 2024-01-15 12:00 UTC (UTC == GMT, i.e. Irish winter)
        self._now: datetime = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

    # ------------------------------------------------------------------ setup

    def set_now(self, dt: datetime) -> "HAEnv":
        """Set the datetime returned by now()."""
        self._now = dt
        return self

    def set_state(self, entity_id: str, state: str, **attributes: Any) -> "HAEnv":
        """Register a mock entity state (and optional attributes)."""
        self._store[entity_id] = MockState(entity_id, str(state), attributes)
        return self

    # ----------------------------------------------------------------- render

    def render(self, template_str: str) -> str:
        """Render a Jinja2 template string and return the stripped result.

        Normalises Jinja2 boolean output to HA's on/off convention so that
        templates using compact expressions like ``{{ power > 1900 }}`` behave
        the same as explicit ``'on' if ... else 'off'`` forms.
        """
        env = self._build_jinja_env()
        result = env.from_string(template_str).render().strip()
        return {"True": "on", "False": "off"}.get(result, result)

    # --------------------------------------------------------- private helpers

    def _build_jinja_env(self) -> Environment:
        jenv = Environment()

        # HA globals
        now_dt = self._now
        states_proxy = StatesProxy(self._store)

        jenv.globals["now"] = lambda: now_dt
        jenv.globals["states"] = states_proxy
        jenv.globals["is_state"] = lambda eid, s: states_proxy(eid) == s
        jenv.globals["state_attr"] = (
            lambda eid, attr: self._store[eid].attributes.get(attr)
            if eid in self._store else None
        )
        jenv.globals["as_timestamp"] = self._as_timestamp
        jenv.globals["timestamp_custom"] = self._timestamp_custom

        # Python builtins used in templates
        jenv.globals.update(dict=dict, range=range, float=float, int=int)

        # Filters that HA adds on top of Jinja2 defaults
        jenv.filters["float"] = lambda v, default=0.0: _safe_float(v, default)
        jenv.filters["int"] = lambda v, default=0: _safe_int(v, default)
        jenv.filters["round"] = lambda v, precision=0, method="common": (
            round(_safe_float(v), int(precision))
        )
        jenv.filters["abs"] = lambda v: abs(_safe_float(v))

        return jenv

    @staticmethod
    def _as_timestamp(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, datetime):
            return value.timestamp()
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).timestamp()
            except ValueError:
                return None
        return None

    @staticmethod
    def _timestamp_custom(value: float, fmt: str, local: bool = True) -> str:
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        return dt.strftime(fmt)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def load_template_state(filename: str, unique_id: str) -> str:
    """
    Load a sensor/binary_sensor template's ``state:`` block from a YAML file
    in the ``template/`` directory.

    Raises KeyError if the unique_id is not found.
    """
    import yaml  # local import so conftest stays importable without pyyaml installed

    path = os.path.join(TEMPLATE_DIR, filename)
    with open(path) as fh:
        data = yaml.safe_load(fh)

    for block in (data or []):
        if not isinstance(block, dict):
            continue
        for domain in ("sensor", "binary_sensor", "switch"):
            items = block.get(domain) or []
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("unique_id") == unique_id:
                    state = item.get("state", "")
                    return state if isinstance(state, str) else str(state)

    raise KeyError(
        f"No sensor/binary_sensor with unique_id={unique_id!r} found in template/{filename}"
    )


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ha_env() -> HAEnv:
    """Fresh HAEnv for each test."""
    return HAEnv()


@pytest.fixture
def ha_root() -> str:
    return HA_ROOT
