"""
Structural validation tests for all YAML config files.

These tests parse the YAML and assert structural correctness without running
any templates.  They catch:
  - MQTT device-ID typos (payload_on vs payload_off address mismatch)
  - Missing unique_id / name on entities
  - Unnamed valve entities
  - Template sensors without unique_id
  - Electricity rate schedule entity name typos

Run with:
    pytest tests/ha_config/test_yaml_structure.py -v
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import HA_ROOT, MQTT_DIR, TEMPLATE_DIR  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load(path: str) -> any:
    with open(path) as fh:
        return yaml.safe_load(fh)


def _device_id_from_payload(payload: str | None) -> str | None:
    """Extract Zigbee device address from a ZbSend payload string, e.g. '0x80F8'."""
    if not payload:
        return None
    m = re.search(r'"device"\s*:\s*"(0x[0-9A-Fa-f]+)"', payload)
    return m.group(1).upper() if m else None


# ---------------------------------------------------------------------------
# MQTT switches — device ID consistency
# ---------------------------------------------------------------------------

class TestMqttSwitches:
    """payload_on and payload_off must reference the same Zigbee device address."""

    SWITCHES_FILE = os.path.join(MQTT_DIR, "switches.yaml")

    @pytest.fixture(scope="class")
    def switches(self):
        data = load(self.SWITCHES_FILE)
        result = []
        for block in data:
            if isinstance(block, dict):
                items = block.get("switch") or []
                if isinstance(items, list):
                    result.extend(items)
        return result

    def test_all_switches_have_unique_id(self, switches):
        missing = [s.get("name", "<unnamed>") for s in switches if not s.get("unique_id")]
        assert missing == [], f"Switches missing unique_id: {missing}"

    def test_payload_on_and_off_reference_same_device(self, switches):
        """
        Catches the office_socket bug: payload_on uses '0x280F8' but
        payload_off uses '0x80F8' — one of them is a typo.
        """
        mismatches = []
        for switch in switches:
            on_id = _device_id_from_payload(switch.get("payload_on"))
            off_id = _device_id_from_payload(switch.get("payload_off"))
            if on_id and off_id and on_id != off_id:
                mismatches.append(
                    f"{switch.get('unique_id', switch.get('name', '?'))}: "
                    f"payload_on={on_id!r} vs payload_off={off_id!r}"
                )
        assert mismatches == [], (
            "MQTT switch payload_on / payload_off device addresses don't match:\n"
            + "\n".join(f"  {m}" for m in mismatches)
        )

    def test_all_switches_have_state_topic(self, switches):
        missing = [s.get("unique_id", "?") for s in switches if not s.get("state_topic")]
        assert missing == [], f"Switches missing state_topic: {missing}"


# ---------------------------------------------------------------------------
# MQTT sensors — availability topic consistency
# ---------------------------------------------------------------------------

class TestMqttSensors:
    SENSORS_FILE = os.path.join(MQTT_DIR, "sensors.yaml")

    @pytest.fixture(scope="class")
    def sensors(self):
        data = load(self.SENSORS_FILE)
        result = []
        for block in data:
            if isinstance(block, dict):
                items = block.get("sensor") or []
                if isinstance(items, list):
                    result.extend(items)
        return result

    def test_all_sensors_have_availability_topic(self, sensors):
        missing = [s.get("name", "?") for s in sensors if not s.get("availability_topic")]
        assert missing == [], f"Sensors without availability_topic: {missing}"

    def test_all_sensors_have_unit(self, sensors):
        missing = [s.get("name", "?") for s in sensors if not s.get("unit_of_measurement")]
        assert missing == [], f"Sensors without unit_of_measurement: {missing}"


# ---------------------------------------------------------------------------
# MQTT valves — must have a name
# ---------------------------------------------------------------------------

class TestMqttValves:
    VALVES_FILE = os.path.join(MQTT_DIR, "valves.yaml")

    def test_all_valves_have_name(self):
        data = load(self.VALVES_FILE)
        for block in data:
            if not isinstance(block, dict):
                continue
            items = block.get("valve") or []
            for valve in items:
                if isinstance(valve, dict):
                    # name can be None/empty string — flag those
                    name = valve.get("name")
                    assert name, (
                        f"Valve unique_id={valve.get('unique_id')!r} has no name set. "
                        "An unnamed valve appears as 'None' in the HA UI."
                    )


# ---------------------------------------------------------------------------
# MQTT binary sensors — consistent payload structure
# ---------------------------------------------------------------------------

class TestMqttBinarySensors:
    FILE = os.path.join(MQTT_DIR, "binary_sensors.yaml")

    @pytest.fixture(scope="class")
    def binary_sensors(self):
        data = load(self.FILE)
        result = []
        for block in data:
            if isinstance(block, dict):
                items = block.get("binary_sensor") or []
                if isinstance(items, list):
                    result.extend(items)
        return result

    def test_all_have_name(self, binary_sensors):
        missing = [s for s in binary_sensors if not s.get("name")]
        assert missing == [], f"{len(missing)} binary sensors have no name"

    def test_all_have_state_topic(self, binary_sensors):
        missing = [s.get("name", "?") for s in binary_sensors if not s.get("state_topic")]
        assert missing == [], f"Binary sensors missing state_topic: {missing}"


# ---------------------------------------------------------------------------
# Template sensors — all should have unique_id
# ---------------------------------------------------------------------------

class TestTemplateSensorUniqueIds:
    """
    Every template sensor/binary_sensor should have a unique_id so HA can
    track it across restarts and allow customisation via the UI.
    """

    @pytest.fixture(scope="class")
    def all_template_entities(self):
        entities = []
        for fname in Path(TEMPLATE_DIR).glob("*.yaml"):
            data = load(str(fname))
            for block in (data or []):
                if not isinstance(block, dict):
                    continue
                for domain in ("sensor", "binary_sensor", "switch"):
                    items = block.get(domain) or []
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                item["_source_file"] = fname.name
                                entities.append(item)
        return entities

    def test_all_template_entities_have_unique_id(self, all_template_entities):
        missing = [
            f"{e['_source_file']} → {e.get('name', '<unnamed>')}"
            for e in all_template_entities
            if not e.get("unique_id")
        ]
        assert missing == [], (
            "Template entities without unique_id (HA can't track them across restarts):\n"
            + "\n".join(f"  {m}" for m in missing)
        )

    def test_worldtidesinfo_template_is_orphaned(self):
        """
        template/tide.yaml still references sensor.worldtidesinfo which has been
        replaced by met_ie_buoy.  This test will PASS once that file is removed.
        """
        tide_file = os.path.join(TEMPLATE_DIR, "tide.yaml")
        if not os.path.exists(tide_file):
            pytest.skip("tide.yaml already removed — nothing to check")

        with open(tide_file) as fh:
            content = fh.read()

        assert "worldtidesinfo" not in content, (
            "template/tide.yaml still references sensor.worldtidesinfo which no longer "
            "exists (replaced by met_ie_buoy tide sensors). "
            "Delete or update this file."
        )


# ---------------------------------------------------------------------------
# Configuration.yaml — electricity schedule name typos
# ---------------------------------------------------------------------------

class TestConfigurationYaml:
    CONFIG_FILE = os.path.join(HA_ROOT, "configuration.yaml")

    def test_no_electricity_schedule_typos(self):
        """
        Schedule entities are named 'Electrcity ...' (missing the 'i').
        This test flags them so they can be renamed to 'Electricity ...'.
        NOTE: After renaming, update every automation/template that uses
        schedule.electrcity_* entity IDs.
        """
        with open(self.CONFIG_FILE) as fh:
            content = fh.read()

        typo_count = content.count("Electrcity")
        assert typo_count == 0, (
            f"Found {typo_count} occurrence(s) of 'Electrcity' in configuration.yaml "
            "(should be 'Electricity'). Fix the schedule names and update all entity_id "
            "references in automations and templates."
        )

    def test_electricity_schedule_entities_exist(self):
        """Verify that the electricity schedule helper section is present."""
        with open(self.CONFIG_FILE) as fh:
            content = fh.read()
        assert "schedule:" in content.lower() or "electricity" in content.lower(), (
            "No electricity schedule found in configuration.yaml"
        )


# ---------------------------------------------------------------------------
# Stale / dead template sensors
# ---------------------------------------------------------------------------

class TestStaleTemplates:
    """Flag template sensors from previous electricity suppliers that are no longer needed."""

    RATE_FILE = os.path.join(TEMPLATE_DIR, "electricity_rate.yaml")

    def test_bge_rate_sensor_removed(self):
        """
        The BGÉ rate sensor was for a previous supplier.
        Remove it to reduce unnecessary template evaluation overhead.
        If you are back on BGÉ, delete this test.
        """
        if not os.path.exists(self.RATE_FILE):
            pytest.skip("electricity_rate.yaml not found")
        with open(self.RATE_FILE) as fh:
            content = fh.read()
        assert "bge_rate" not in content, (
            "electricity_rate.yaml still contains the bge_rate sensor for a previous "
            "supplier. Remove it if you are no longer on BGÉ."
        )

    def test_energia_rate_sensor_removed(self):
        """Same as above for the Energia rate sensor."""
        if not os.path.exists(self.RATE_FILE):
            pytest.skip("electricity_rate.yaml not found")
        with open(self.RATE_FILE) as fh:
            content = fh.read()
        assert "energia_rate" not in content, (
            "electricity_rate.yaml still contains the energia_rate sensor for a previous "
            "supplier. Remove it if you are no longer on Energia."
        )
