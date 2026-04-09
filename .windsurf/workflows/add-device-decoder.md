---
description: Add support for a new device model
---

## Steps to add a new device decoder

1. **Create decoder file** at `custom_components/homgar/api/decoders/<model_lower>.py`
   - Parse the raw hex payload (strips `NN#` prefix via `_parse_homgar_payload` from `api/utils.py`)
   - For EU ASCII format payloads use `_parse_ascii_sensor_payload` from `api/utils.py`
   - Return a dict with typed fields (e.g. `temperature_c`, `humidity_percent`, `battery_percent`, `rssi_dbm`)

2. **Export from `api/decoders/__init__.py`** — add `from .mymodel import decode_mymodel` and add to `__all__`

3. **Export from `api/__init__.py`** — add to imports and `__all__`

4. **Export from `homgar_api.py`** — add to the `from .api import (...)` block and `__all__`

5. **Add model constant to `const.py`**:
   ```python
   MODEL_MYMODEL = "MYMODEL"
   ```

6. **Register in `DECODER_REGISTRY` in `coordinator.py`**:
   ```python
   MODEL_MYMODEL: decode_mymodel,
   ```
   This automatically enables both REST poll and real-time MQTT decoding.

7. **Add sensor entities in `sensor.py`**:
   - Add `MODEL_MYMODEL` to the relevant `if model in (...)` branch, or create new entity classes
   - Import the new constant

8. **For valve/timer sub-devices** — no extra changes needed; `coordinator_mqtt.py` uses `DECODER_REGISTRY` automatically via sub-device lookup from `hub["subDevices"]`

9. **Add test payload** to `scripts/pre-commit-docker-test.sh`

10. **Run tests**:
```
bash scripts/pre-commit-docker-test.sh
```

## Payload format notes
- US binary format: `NN#HEXSTRING` where `NN` is a byte count tag
- EU ASCII format: `battery,rssi;value1(max/min/trend),value2,...`
- Use `_parse_homgar_payload(raw)` to get `bytes` from US format
- Valve sub-devices are looked up by `addr` from `hub["subDevices"]` list at MQTT time
