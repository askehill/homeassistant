# Home Assistant Configuration

[![Tests](https://github.com/askehill/homeassistant/actions/workflows/tests.yml/badge.svg)](https://github.com/askehill/homeassistant/actions/workflows/tests.yml)

Personal Home Assistant configuration for an Irish home. Zigbee devices are bridged via a Tasmota-flashed Sonoff Zigbee Bridge (zbbridge); RF devices (blinds, some motion sensors) via a Tasmota-flashed RF Bridge (rfbridge). Energy monitoring uses Shelly devices. Heating is zone-based using generic thermostats driven by Zigbee temperature sensors.

`secrets.yaml` is excluded from this repo — see `dummy_secrets.yaml` for the required keys.

---

## Repository layout

```
configuration.yaml      # Top-level HA config; includes all sub-files
automations.yaml        # All automations (single file)
scripts.yaml / scenes.yaml / switches.yaml / lights.yaml / climate.yaml
template/               # Template sensors & binary sensors (one file per domain)
mqtt/                   # MQTT entities split by type (sensors, switches, lights, …)
tests/                  # pytest suite — template logic, YAML structure, entity linting
python_scripts/         # shellies_discovery helper
```

---

## Integrations

| Integration | Purpose |
|---|---|
| Tasmota ZbBridge (`tele/zbbridge`) | Zigbee sensors, switches, lights, valves, door/motion sensors |
| Tasmota RfBridge (`tele/rfbridge`) | RF motion sensors, blinds, hotpress light switch |
| Shelly (various) | Energy monitoring, switching, and sensing |
| Samsung SmartThings | Washing machine (`select.washing_machine`: Running / Stopped / Paused) |
| SPC Alarm | Intruder alarm (API + WebSocket via `spc:`) |
| Google Assistant | Voice control via service account |
| met_ie_buoy (custom) | M2 buoy sea conditions + Dublin tide predictions |
| generic_thermostat | Zone heating (Living Room, Kitchen, Study, Master Bedroom) |

For the full hardware inventory — Zigbee hex IDs, RF codes, and Shelly MAC addresses — see [DEVICES.md](DEVICES.md).

---

## Electricity tariff (Electric Ireland Weekender)

Tracked via `sensor.electricity_rate` and four `utility_meter` tariffs.

| Tariff | Times |
|---|---|
| Night | 23:00 – 08:00 daily |
| Off-Peak | 08:00 – 17:00 and 19:00 – 23:00 daily |
| Peak | 17:00 – 19:00 Mon–Sat |
| Weekend (free) | 08:00 – 23:00 Sunday |

Automations switch the active `utility_meter` tariff at each boundary.

---

## Template sensors (template/)

| File | What it provides |
|---|---|
| `electricity_rate.yaml` | Current €/kWh rate and tariff name |
| `laundry.yaml` | Washing machine and tumble dryer running state (single-clamp inference); dishwasher and hot water tap state |
| `gas.yaml` | Gas usage estimation |
| `occupancy.yaml` | Room-level occupancy derived from motion and door sensors |
| `shower.yaml` | Shower running binary sensor |
| `sun.yaml` | Derived sun conditions (e.g. "dark enough" threshold) |
| `misc.yaml` | Miscellaneous helper sensors |
| `evcharger.yaml` | EV charger state |
| `switches.yaml` | Template switch helpers |
| `water_volume.yaml` | Water butt volume estimation |

### Laundry single-clamp logic

The laundry clamp covers both the washing machine and the heat pump tumble dryer. The Samsung washing machine exposes `select.washing_machine` (Running / Stopped / Paused), which is used as an anchor:

- If washer is Stopped or Paused → all clamp power is attributed to the dryer.
- If washer is Running → subtract an estimated washer draw (2000 W during heating, 400 W otherwise) and treat the residual as dryer power.
- Dryer is considered "on" if its attributed power exceeds 400 W.

The dishwasher and hot water tap share a separate Shelly PM Mini clamp. Dishwasher threshold is >1900 W with a 20-minute `delay_off` to bridge the gaps between cycles.

---

## Testing

The `tests/` directory contains a pytest suite that runs without a live HA instance.

```bash
# one-time setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-test.txt

# run all tests
pytest
```

Three test modules:

- `test_templates.py` — renders template Jinja2 logic against a mock HA environment and asserts correct on/off outputs across a range of power readings and states.
- `test_yaml_structure.py` — validates MQTT device ID consistency, unique_id uniqueness, valve naming, and checks for known typos/stale sensors.
- `test_entity_refs.py` — lints all YAML files for entity ID references that don't match known HA naming conventions.

---

## Security notes

`secrets.yaml` is excluded via `.gitignore`. The `dummy_secrets.yaml` file shows required secret keys with placeholder values. NFC tag IDs and alarm codes are stored only in `secrets.yaml` and are never committed.
