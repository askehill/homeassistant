# CLAUDE.md — Session context for AI assistants

This file helps an AI assistant pick up where a previous session left off without re-reading every file from scratch.

---

## What this repo is

Home Assistant configuration. Not a software project — YAML config files that are loaded directly by a running HA instance. The "code" is Jinja2 templates inside YAML. The test suite (pytest) validates that template logic and YAML structure are correct without requiring a live HA instance.

---

## Architecture decisions made (and why)

### Timezone comparisons
Heating automations need to distinguish GMT (winter) from IST (summer). The original code compared `tzinfo | string` against the literal string "GMT" — fragile because HA's string representation can change. Replaced with:
```yaml
"{{ now().utcoffset().total_seconds() == 0 }}"      # GMT
"{{ now().utcoffset().total_seconds() == 3600 }}"   # IST
```

### Heating trigger strategy
Winter heating has a dual trigger: sunset+5min OR 16:30. This handles October/March shoulder months where sunset is still before 16:30 but the day is short enough that the elevation check misses it. The condition `state_attr('sun.sun', 'elevation') < 10` acts as a "dark enough" floor so the 16:30 trigger doesn't fire in summer.

### Lighting split
What was a single automation with a `delay:` in a script was split into two independent automations: indoor at sunset, outdoor at sunset+10min (using trigger `offset: 00:10:00`). Script delays are fragile across HA restarts; offset triggers are not.

### Unsafe toggle
`input_boolean.toggle` was replaced with `turn_on` in heating automations. Toggle is only safe when you know the current state; at automation trigger time that's not guaranteed.

### Laundry single-clamp inference
`sensor.laundry_power` covers both washing machine (Samsung SmartThings) and heat pump tumble dryer (dumb). Samsung exposes `select.washing_machine` with states: Running / Stopped / Paused.

Logic in `template/laundry.yaml`:
- Washer Stopped or Paused → all power = dryer
- Washer Running + total > 1500 W → subtract 2000 W (heating cycle), residual = dryer
- Washer Running + total ≤ 1500 W → subtract 400 W (rinse/spin), residual = dryer
- Dryer "on" threshold: residual > 400 W

The heat pump dryer draws 500–900 W while heating, 100–300 W in cool-down.

### Dishwasher vs hot water tap (single clamp)
`sensor.shellypmmini_543204b7d0c0_power` covers both. Hot water tap standby is ~2 W. Dishwasher detection uses `current_power > 1900` with `delay_off: minutes: 20` to bridge power gaps between wash cycles. Hot water tap detection uses `1100 < current_power < 1500`.

---

## Test suite (tests/)

Run with: `pytest` from repo root (requires `.venv` — see README).

| File | What it tests |
|---|---|
| `tests/conftest.py` | `HAEnv` mock — Jinja2 environment with mockable `states()`, `now()`, `is_state()`, `state_attr()`. `StatesProxy` supports both `states('entity.id')` call syntax and `states.domain` list syntax. `render()` normalises Jinja2 `True`/`False` → `on`/`off` to match HA's internal behaviour. |
| `tests/ha_config/test_templates.py` | Template logic tests — electricity rate, laundry appliances, dishwasher, hot water tap, gas, occupancy, shower, sun, heating timezone comparisons. |
| `tests/ha_config/test_yaml_structure.py` | YAML structure validation — MQTT device ID consistency, unique_id uniqueness per domain, valve naming, worldtidesinfo orphan check, stale sensor check, typo check. |
| `tests/ha_config/test_entity_refs.py` | Entity reference linter — walks all YAML values, finds strings that look like entity IDs, validates they match known HA domain patterns. Skips hex device IDs (`HEX_ID_RE`). |

### Known test quirks
- `HAEnv.render()` returns `"on"`/`"off"` for templates that render `True`/`False`. Tests must assert `== "on"` / `== "off"`, not `== "True"` / `== "False"`.
- `load_template_state(filename, unique_id)` loads a single `state:` block from a template YAML file — used so tests don't hardcode template strings.
- Hex device IDs (e.g. `0x80F8`) appear under `entity_id` keys in some device-based automations. The entity ref linter skips these via `HEX_ID_RE = re.compile(r'^[0-9a-f]{20,}$')`.

---

## MQTT device structure

All Zigbee devices go through `tele/zbbridge/SENSOR` as a JSON blob keyed by short hex address (e.g. `ZbReceived['0x167A']`). Commands go to `cmnd/zbbridge/ZbSend` as JSON payloads. RF devices go through `tele/rfbridge/RESULT` → `RfReceived.Data`.

See the hex-to-device table in README.md.

---

## Files to know

| File | Notes |
|---|---|
| `configuration.yaml` | Top-level; defines utility_meter tariffs, timers, schedule blocks, includes all sub-files |
| `automations.yaml` | All automations — single flat file, ~40 automations |
| `template/laundry.yaml` | Most complex template logic — see laundry section above |
| `template/electricity_rate.yaml` | Tariff sensor; Electric Ireland Weekender (Sunday free) |
| `climate.yaml` | Four generic_thermostat zones driven by Zigbee temp sensors |
| `mqtt/switches.yaml` | Zigbee smart plugs via zbbridge |
| `mqtt/sensors.yaml` | Zigbee temp/humidity/pressure sensors via zbbridge |
| `dummy_secrets.yaml` | Shows required secret key names — actual values in secrets.yaml (gitignored) |

---

### Water butt volume (two-butt setup)
`template/water_volume.yaml` reads `sensor.shellyuni_c45bbe5f76f8_adc` (Hyuduo 4-20mA submersible sensor, 0-5m range, mounted at the base of the big butt).

Physical setup: 250 L big butt (sensor here) + 100 L small butt connected at 1/4 height of the big butt (~62.5 L mark) and at ~2 cm from the base of the small butt.

Piecewise volume model:
- ADC ≤ 0.179 V → big butt only, linear scale 62.5 L / 0.179 V
- ADC > 0.179 V → both butts filling together, linear scale 287.5 L / 0.535 V
- Clamped: minimum 0 L, maximum 350 L

`big_full_v = 0.714` is derived from the observed calibration point (0.03 V ≈ 10.5 L → 350 L/V). Update this constant once a confirmed full-tank ADC reading is available.

---

## What has NOT been done yet

- `template/electricity_rate.yaml` contains a known stale sensor (`Electric Ireland Weekender (Sunday)`) that duplicates/conflicts with the utility_meter approach — not yet cleaned up.
- Travis CI badge in README is present but `.travis.yml` may be stale (was not reviewed in previous sessions).
- `python_scripts/shellies_discovery.py` was not reviewed.
- `template/evcharger.yaml` and `template/water_volume.yaml` were not reviewed in detail.
