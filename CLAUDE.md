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
- `delay_off: minutes: 15` bridges dryer cool-down phases (100–300 W, below detection threshold)

The heat pump dryer draws 500–900 W while heating, 100–300 W in cool-down.

### Dishwasher vs hot water tap (single clamp)
`sensor.shellypmmini_543204b7d0c0_power` covers both. Hot water tap standby is ~2 W.

- Dishwasher detection: `current_power > 1900` with `delay_off: minutes: 60`. The 60-min delay_off bridges pump-only phases (~18 W) between heating cycles. A 14–600 W band was tried but caused false positives because the hot water tap's keep-warm boiler cycles at ~18–200 W every 10–15 min — indistinguishable from the dishwasher pump on a shared clamp. Reverted to heating-element-only detection.
- Hot water tap detection: `1100 < current_power < 1500`.

### Electricity tariff — Electric Ireland SST
Rates are centralised in `packages/electricity.yaml` as a template sensor (`sensor.electricity_plan_config`) with attributes. `template/electricity_rate.yaml` reads from that sensor via `state_attr()`. This means tariff changes only require editing one file.

Current rates (VAT-inclusive, effective 2025-01-01):
- Night (23:00–08:00): 13.62 c/kWh
- Day (08:00–17:00 and 19:00–23:00): 25.92 c/kWh
- Peak (17:00–19:00, every day): 27.65 c/kWh
- Carbon tax: 1.251 c/kWh (added on top of all bands)
- Standing charge: €250.77/year (charged daily)
- PSO levy: €19.10/year (charged daily)

**To update rates (e.g. July 1st change):** edit only `packages/electricity.yaml`.

### Laundry notifications — entity ID naming rule
HA generates entity IDs from the `name` field, not `unique_id`. A sensor named "Washing Machine Finished" becomes `binary_sensor.washing_machine_finished`. Automations must reference the name-derived entity ID. Previous bug: sensors were named "Complete" but automations referenced `_finished` IDs — notifications never fired. Fixed by renaming to "Finished" throughout.

### Midnight laundry reset — conditional retry
The "Reset laundry notification subscriptions at midnight" automation checks that both `binary_sensor.washing_machine` and `binary_sensor.tumble_dryer` are off before resetting the opt-in booleans. It retries every 15 minutes between 00:00–06:00 if either appliance is still running, to avoid clearing a subscription mid-cycle.

### SmartThings reliability fallback
`select.washing_machine` can get stuck on Running after a cycle completes. The `washing_machine_finished` binary sensor uses:
```
{{ washer != 'Running' or total_w < 100 }}
```
Primary: SmartThings transitions to Stopped/Paused. Fallback: if SmartThings stays on Running but clamp draws <100 W for 3 minutes, treat cycle as done. `delay_on: minutes: 3` — chosen because SmartThings can briefly show Stopped between consecutive cycles (~7 min observed), and 3 min fits safely within that gap.

### Scripts directory split
`scripts.yaml` was split into a `scripts/` directory. `configuration.yaml` uses `!include_dir_merge_named scripts`. The old `scripts.yaml` file should be deleted if it still exists.

---

## Test suite (tests/)

Run with: `pytest` from repo root (requires `.venv` — see README).

| File | What it tests |
|---|---|
| `tests/conftest.py` | `HAEnv` mock — Jinja2 environment with mockable `states()`, `now()`, `is_state()`, `state_attr()`. `StatesProxy` supports both `states('entity.id')` call syntax and `states.domain` list syntax. `render()` normalises Jinja2 `True`/`False` → `on`/`off` to match HA's internal behaviour. `PACKAGES_DIR` path constant added. |
| `tests/ha_config/test_templates.py` | Template logic tests — electricity rate (SST), laundry appliances, dishwasher, hot water tap, gas, occupancy, shower, sun, heating timezone comparisons. |
| `tests/ha_config/test_yaml_structure.py` | YAML structure validation — MQTT device ID consistency, unique_id uniqueness per domain (scans both `template/` and `packages/`), valve naming, worldtidesinfo orphan check, stale sensor check, typo check. |
| `tests/ha_config/test_entity_refs.py` | Entity reference linter — walks all YAML values, finds strings that look like entity IDs, validates they match known HA domain patterns. Skips hex device IDs (`HEX_ID_RE`). Uses `load_scripts_dir()` to merge all files from `scripts/` directory. |

### Known test quirks
- `HAEnv.render()` returns `"on"`/`"off"` for templates that render `True`/`False`. Tests must assert `== "on"` / `== "off"`, not `== "True"` / `== "False"`.
- `load_template_state(filename, unique_id)` loads a single `state:` block from a template YAML file — used so tests don't hardcode template strings.
- Hex device IDs (e.g. `0x80F8`) appear under `entity_id` keys in some device-based automations. The entity ref linter skips these via `HEX_ID_RE = re.compile(r'^[0-9a-f]{20,}$')`.
- Electricity rate tests use `_seed_config()` to mock `sensor.electricity_plan_config` with test attribute values before rendering rate templates.
- `test_bbc_radio_script_alias_matches_content` skips values containing `{{` (Jinja2 expressions) to avoid false positives from parameterised station names.

---

## MQTT device structure

All Zigbee devices go through `tele/zbbridge/SENSOR` as a JSON blob keyed by short hex address (e.g. `ZbReceived['0x167A']`). Commands go to `cmnd/zbbridge/ZbSend` as JSON payloads. RF devices go through `tele/rfbridge/RESULT` → `RfReceived.Data`.

See the hex-to-device table in README.md.

---

## Files to know

| File | Notes |
|---|---|
| `configuration.yaml` | Top-level; defines utility_meter tariffs, timers, schedule blocks, includes all sub-files. `homeassistant:` section includes `packages: !include_dir_named packages`. |
| `automations.yaml` | All automations — single flat file, ~40 automations |
| `packages/electricity.yaml` | **Single source of truth for electricity tariff rates.** Edit this when rates change. |
| `template/laundry.yaml` | Most complex template logic — see laundry section above |
| `template/electricity_rate.yaml` | Tariff sensor — reads rates from `sensor.electricity_plan_config` via `state_attr()` |
| `scripts/` | Scripts directory (split from scripts.yaml) — loaded via `!include_dir_merge_named` |
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

### Laundry notification opt-in
Four `input_boolean` helpers (defined in `configuration.yaml`) act as per-device opt-in flags for washing machine and tumble dryer completion notifications. Each is reset to `off` at midnight by the "Reset laundry notification subscriptions at midnight" automation (with conditional retry — see above).

Two scripts (`toggle_washing_notification`, `toggle_dryer_notification`) use `context.user_id` to detect who pressed the Lovelace button, toggle that person's boolean, and send a confirmation notification to their device. User ID → device mapping:

- `c84aab97a0c643c4bc2ee284cbb95ce8` → `notify.mobile_app_cph2581`
- `caeb45de55f14787ad9f32e6172bb085` → `notify.mobile_app_pixel_8`

To add a new device: add a new `input_boolean` pair in `configuration.yaml`, add a new `choose` branch in each script with the new user's ID, and add a new `if` block in each of the two notify automations.

---

## What has NOT been done yet

- Travis CI badge in README is present but `.travis.yml` may be stale (was not reviewed).
- `python_scripts/shellies_discovery.py` was not reviewed.
- `template/evcharger.yaml` was not reviewed in detail.
- 10 unidentified Shelly devices in DEVICES.md — not yet mapped.
- `big_full_v` constant in `template/water_volume.yaml` needs updating once a confirmed full-tank ADC reading is available.
- Dynamic electricity pricing (July 2026): monitor Irish supplier APIs and HA community integrations. `packages/electricity.yaml` is ready to be updated when dynamic tariff is activated.
