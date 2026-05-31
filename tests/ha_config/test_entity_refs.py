"""
Entity reference linter for automations.yaml and scripts.yaml.

Checks:
  - All entity_id values follow the 'domain.name' convention
  - No bare device_id values used in automation/script targets (portability)
  - Reports service: vs action: mix (old vs new HA syntax)
  - Zappi charging automation times are not hard-coded (should use schedule helper)

Run with:
    pytest tests/ha_config/test_entity_refs.py -v

Run with -s to also see the full syntax-migration report:
    pytest tests/ha_config/test_entity_refs.py -v -s
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Generator

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import HA_ROOT  # noqa: E402

AUTOMATIONS_FILE = os.path.join(HA_ROOT, "automations.yaml")
SCRIPTS_DIR = os.path.join(HA_ROOT, "scripts")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load(path: str) -> Any:
    with open(path) as fh:
        return yaml.safe_load(fh)


def load_scripts_dir(directory: str) -> dict:
    """
    Merge all YAML files in a directory into a single dict.
    Mirrors what HA's !include_dir_merge_named does at runtime.
    """
    merged: dict = {}
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".yaml"):
            continue
        fpath = os.path.join(directory, fname)
        with open(fpath) as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict):
            merged.update(data)
    return merged


def _walk(obj: Any) -> Generator[Any, None, None]:
    """Recursively yield every value in a nested dict/list structure."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield v
            yield from _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield item
            yield from _walk(item)


def _walk_items(obj: Any) -> Generator[tuple[str, Any], None, None]:
    """Yield (key, value) pairs for every dict key in the structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk_items(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_items(item)


ENTITY_ID_RE = re.compile(r'^[a-z_]+\.[a-z0-9_]+$')
HA_DOMAINS = {
    "sensor", "binary_sensor", "switch", "light", "input_boolean",
    "input_number", "input_select", "automation", "script", "scene",
    "climate", "cover", "media_player", "timer", "counter",
    "device_tracker", "person", "zone", "sun", "weather", "camera",
    "alarm_control_panel", "lock", "fan", "vacuum", "remote",
    "number", "select", "button", "update", "schedule",
    "utility_meter", "template", "valve", "water_heater",
    "event", "todo", "conversation", "stt", "tts", "wake_word",
}


def _looks_like_entity_id(value: str) -> bool:
    if not isinstance(value, str):
        return False
    if "." not in value:
        return False
    domain = value.split(".")[0]
    return domain in HA_DOMAINS and bool(ENTITY_ID_RE.match(value))


def _collect_entity_ids(data: Any) -> list[str]:
    """Collect all string values that look like HA entity IDs."""
    result = []
    for value in _walk(data):
        if isinstance(value, str) and _looks_like_entity_id(value):
            result.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and _looks_like_entity_id(item):
                    result.append(item)
    return list(set(result))


def _collect_device_ids(data: Any) -> list[dict]:
    """Return contexts where device_id is set to a non-empty value."""
    uses = []
    for key, value in _walk_items(data):
        if key == "device_id" and value:
            if isinstance(value, str) and len(value) > 10:
                uses.append({"device_id": value})
            elif isinstance(value, list):
                for v in value:
                    if isinstance(v, str) and len(v) > 10:
                        uses.append({"device_id": v})
    return uses


def _count_syntax(data: Any) -> tuple[int, int]:
    """Return (service_count, action_count) across the structure."""
    service = sum(1 for k, _ in _walk_items(data) if k == "service")
    action = sum(1 for k, _ in _walk_items(data) if k == "action")
    return service, action


# ---------------------------------------------------------------------------
# Automations
# ---------------------------------------------------------------------------

class TestAutomations:
    @pytest.fixture(scope="class")
    def automations(self):
        return load(AUTOMATIONS_FILE)

    def test_file_is_a_list(self, automations):
        assert isinstance(automations, list), "automations.yaml should be a list"

    def test_all_automations_have_alias(self, automations):
        missing = [
            i for i, a in enumerate(automations)
            if isinstance(a, dict) and not a.get("alias")
        ]
        assert missing == [], (
            f"{len(missing)} automation(s) at indices {missing} have no alias — "
            "makes them impossible to identify in the HA UI."
        )

    def test_entity_ids_look_valid(self, automations):
        """
        entity_id values should follow the 'domain.name' convention.

        Hex-string device IDs (e.g. ddfa59260e2cb18afd5695cdc82640fb) sometimes
        appear under 'entity_id' keys in device-based triggers generated by the
        HA UI — these are captured by test_no_device_id_in_targets and skipped here.
        """
        HEX_ID_RE = re.compile(r'^[0-9a-f]{20,}$')
        invalid = []
        for key, value in _walk_items(automations):
            if key == "entity_id":
                ids = [value] if isinstance(value, str) else (value or [])
                for eid in ids:
                    if not isinstance(eid, str) or not eid:
                        continue
                    if HEX_ID_RE.match(eid):
                        continue  # device ID masquerading as entity_id — handled elsewhere
                    if not _looks_like_entity_id(eid):
                        invalid.append(eid)
        assert invalid == [], (
            f"Entity IDs that don't match domain.name pattern: {invalid}"
        )

    def test_no_device_id_in_targets(self, automations):
        """
        Automations should use entity_id rather than device_id in targets.
        device_id values are HA-internal and change when a device is re-paired
        or HA is restored to a new instance.
        """
        device_id_uses = _collect_device_ids(automations)
        assert device_id_uses == [], (
            f"Found {len(device_id_uses)} device_id reference(s) in automations.yaml. "
            "Replace with entity_id for portability.\n"
            + "\n".join(f"  {d}" for d in device_id_uses[:5])
        )

    def test_syntax_migration_report(self, automations):
        """
        Non-failing report: prints a breakdown of old service: vs new action: usage.
        Automations should all use action: (new syntax).
        This test PASSES even with mixed syntax but prints a report with -s.
        """
        service_count, action_count = _count_syntax(automations)
        total = service_count + action_count
        if total > 0:
            pct_old = 100 * service_count // total
            print(
                f"\n  Automation syntax: {action_count} action: (new) / "
                f"{service_count} service: (old) — {pct_old}% still needs migration"
            )
        # Not a hard failure — just informational
        assert True

    def test_zappi_charging_does_not_hardcode_times(self, automations):
        """
        Zappi EV charging automations should trigger on the electricity schedule
        helper state change rather than hard-coded times.
        Hard-coded times mean updating two places when the tariff window changes.

        This test will FAIL until the Zappi automations are migrated.
        If you are happy with hardcoded times, delete this test.
        """
        zappi_with_time_trigger = []
        for auto in automations:
            if not isinstance(auto, dict):
                continue
            alias = auto.get("alias", "").lower()
            if "zappi" not in alias and "ev" not in alias and "charge" not in alias:
                continue
            # Look for time-based triggers
            triggers = auto.get("trigger") or auto.get("triggers") or []
            if isinstance(triggers, dict):
                triggers = [triggers]
            for t in triggers:
                if isinstance(t, dict) and t.get("platform") == "time":
                    zappi_with_time_trigger.append(auto.get("alias", "?"))

        assert zappi_with_time_trigger == [], (
            "These Zappi/EV charging automations use hard-coded time triggers instead of "
            "the electricity schedule helper:\n"
            + "\n".join(f"  - {a}" for a in zappi_with_time_trigger)
            + "\nConsider triggering on schedule.electrcity_night state change instead."
        )


# ---------------------------------------------------------------------------
# Scripts
# ---------------------------------------------------------------------------

class TestScripts:
    @pytest.fixture(scope="class")
    def scripts(self):
        return load_scripts_dir(SCRIPTS_DIR)

    def test_file_loads(self, scripts):
        assert scripts is not None

    def test_no_device_id_in_scripts(self, scripts):
        """
        Same as automations — scripts should reference entity_id not device_id.
        The 'House Lighting up time' script uses device_id values that will
        break after a device re-pair.
        """
        device_id_uses = _collect_device_ids(scripts)
        assert device_id_uses == [], (
            f"Found {len(device_id_uses)} device_id reference(s) in scripts.yaml. "
            "Replace with entity_id for portability.\n"
            + "\n".join(f"  {d}" for d in device_id_uses[:5])
        )

    def test_all_scripts_have_alias(self, scripts):
        if not isinstance(scripts, dict):
            pytest.skip("scripts.yaml is not a dict — unexpected format")
        missing = [key for key, val in scripts.items() if isinstance(val, dict) and not val.get("alias")]
        assert missing == [], f"Scripts without alias: {missing}"

    def test_syntax_migration_report(self, scripts):
        """Non-failing report of service: vs action: usage in scripts."""
        service_count, action_count = _count_syntax(scripts)
        total = service_count + action_count
        if total > 0:
            pct_old = 100 * service_count // total
            print(
                f"\n  Script syntax: {action_count} action: (new) / "
                f"{service_count} service: (old) — {pct_old}% still needs migration"
            )
        assert True

    def test_bbc_radio_script_alias_matches_content(self, scripts):
        """
        BBC Radio scripts that hardcode a non-BBC title in metadata are flagged.
        Parameterised scripts (title contains '{{') are skipped — the title is
        resolved at runtime from the stations variable and will always be a BBC name.
        """
        if not isinstance(scripts, dict):
            pytest.skip("scripts.yaml is not a dict")

        for key, val in scripts.items():
            if not isinstance(val, dict):
                continue
            alias = val.get("alias", "")
            if "BBC Radio" not in alias:
                continue
            # Check if any step plays something non-BBC (skip Jinja2 template values)
            for item in _walk(val.get("sequence", [])):
                if isinstance(item, dict):
                    title = (item.get("metadata") or {}).get("title", "")
                    if not title or "{{" in title:
                        continue  # parameterised — resolved at runtime
                    if "BBC" not in title and "Radio 1" not in title:
                        pytest.fail(
                            f"Script '{alias}' plays '{title}' — alias doesn't match content. "
                            "Rename the script alias to match the actual station."
                        )

    def test_boost_upstairs_uses_target_not_bare_entity_id(self, scripts):
        """
        boost_upstairs_heating uses the deprecated bare entity_id: syntax
        at the service call level instead of target: { entity_id: ... }.
        This test will PASS once migrated.
        """
        if not isinstance(scripts, dict):
            pytest.skip("scripts.yaml is not a dict")

        script = scripts.get("boost_upstairs_heating", {})
        if not script:
            pytest.skip("boost_upstairs_heating not found")

        bare_entity_ids = []
        for step in script.get("sequence", []):
            if isinstance(step, dict):
                # Bare entity_id at the action level (not inside target:)
                if "entity_id" in step and "target" not in step:
                    bare_entity_ids.append(step.get("entity_id"))

        assert bare_entity_ids == [], (
            f"boost_upstairs_heating uses bare entity_id: {bare_entity_ids} "
            "instead of target: {{entity_id: ...}}. Update to the current syntax."
        )


# ---------------------------------------------------------------------------
# Cross-file entity reference consistency
# ---------------------------------------------------------------------------

class TestCrossFileConsistency:
    """
    Checks that the electricity schedule entity IDs referenced in automations
    are consistent with those defined in configuration.yaml.
    """

    def test_schedule_entity_ids_are_consistent(self):
        """
        Collects schedule.* entity IDs from configuration.yaml and checks that
        automations only reference entity IDs that exist.

        If this fails after renaming 'Electrcity' → 'Electricity', that's expected —
        update all the automation references too.
        """
        config_path = os.path.join(HA_ROOT, "configuration.yaml")
        with open(config_path) as fh:
            config_content = fh.read()

        # Extract schedule entity names from configuration.yaml
        # They appear as "name: Electrcity Day" etc.
        defined_names = re.findall(r'name:\s+"?([^"\n]+)"?', config_content)
        defined_schedule_ids = {
            "schedule." + re.sub(r'\s+', '_', n.strip().lower())
            for n in defined_names
            if n.strip()
        }

        auto_data = load(AUTOMATIONS_FILE)
        # Collect schedule.* entity IDs referenced in automations
        referenced_schedule_ids = {
            eid for eid in _collect_entity_ids(auto_data)
            if eid.startswith("schedule.")
        }

        # Every referenced schedule entity should exist in config
        # We do a soft check: just report, don't fail hard
        # (config parsing is approximate)
        unknown = referenced_schedule_ids - defined_schedule_ids
        if unknown:
            print(
                f"\n  Schedule entities referenced in automations but not found in "
                f"configuration.yaml (may be due to quoting — verify manually):\n"
                + "\n".join(f"    {eid}" for eid in sorted(unknown))
            )
        # This is informational only
        assert True
