# HomGar Cloud integration for Home Assistant

Custom integration for Home Assistant that connects to the HomGar cloud API and exposes RF soil moisture and rain sensors as native HA entities.

Tested with:

- Hub: `HWG023WBRF-V2`
- Soil moisture probes:
  - `HCS026FRF` (moisture-only)
  - `HCS021FRF` (moisture + temperature + lux)
- Rain gauge:
  - `HCS012ARF`

The integration talks to the cloud endpoints used by the HomGar app (`region3.homgarus.com`) and decodes RF payloads into structured sensor data.

## Features

- Login with your HomGar account (email + area code)
- Select which homes to include
- Auto-discovers supported sub-devices
- Exposes:
  - Moisture %
  - Temperature (where applicable)
  - Illuminance (HCS021FRF)
  - Rain:
    - Last hour
    - Last 24 hours
    - Last 7 days
    - Total rainfall
- Attributes:
  - `rssi_dbm`
  - `battery_status_code`
  - `last_updated` (cloud timestamp)

## Installation (HACS - Custom Repository)

1. Go to **HACS → Integrations → 3-dot menu → Custom repositories**
2. Add your repository URL:
   ```
   https://github.com/YOUR_GITHUB_USERNAME/homeassistant-homgar
   ```
3. Category: **Integration**
4. Install
5. Restart Home Assistant

## Manual installation

Copy the folder:

```
custom_components/homgar
```

into:

```
/config/custom_components/
```

Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & services → Add Integration**
2. Search for **HomGar Cloud**
3. Enter:
   - Area code
   - Email
   - Password
4. Select which Home to use
5. Sensors will auto-populate

## Example Automation (Sunrise-based irrigation)

```yaml
alias: Irrigation - morning garden cycle
trigger:
  - platform: sun
    event: sunrise
    offset: "-01:00:00"

condition:
  - condition: template
    value_template: >
      {{ (now().toordinal() % 2) == 0 }}

  - condition: template
    value_template: >
      {% set bottom = states('sensor.bar_side_bottom_moisture_percent')|float(0) %}
      {% set top = states('sensor.bar_side_top_moisture_percent')|float(0) %}
      {% set middle = states('sensor.homgar_garden_middle_moisture_percent')|float(0) %}
      {{ [bottom, top, middle] | min < 35 }}

  - condition: template
    value_template: >
      {% set rain24 = states('sensor.homgar_rain_sensor_rain_last_24h')|float(0) %}
      {% set rain1 = states('sensor.homgar_rain_sensor_rain_last_hour')|float(0) %}
      {{ rain24 < 2 and rain1 < 0.5 }}

action:
  - service: switch.turn_on
    target:
      entity_id: switch.bar_side_garden_irrigation
  - delay: "00:10:00"
  - service: switch.turn_off
    target:
      entity_id: switch.bar_side_garden_irrigation

  - delay: "00:10:00"

  - service: switch.turn_on
    target:
      entity_id: switch.hot_tub_side_garden_irrigation
  - delay: "00:10:00"
  - service: switch.turn_off
    target:
      entity_id: switch.hot_tub_side_garden_irrigation
```

## Troubleshooting

Enable debug logs:

```yaml
logger:
  logs:
    custom_components.homgar: debug
```

Check logs after restart for API or decoder errors.
