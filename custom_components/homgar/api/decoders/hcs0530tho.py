"""Decoder for HCS0530THO CO2 + Temperature + Humidity sensor."""
import logging
from ..utils import _parse_homgar_payload, _parse_ascii_sensor_payload, _parse_stats
from ..validators import _extract_rssi

_LOGGER = logging.getLogger(__name__)


def decode_hcs0530tho(raw: str) -> dict:
    """Decode HCS0530THO (CO2 + Temperature + Humidity) sensor."""
    from ...const import debug_with_version

    _LOGGER.debug(debug_with_version("Decoding HCS0530THO: %s"), raw)

    result = {
        "type": "co2",
        "device_model": "HCS0530THO",
        "co2": None,
        "co2low": None,
        "co2high": None,
        "co2temp": None,
        "co2humidity": None,
        "co2batt": None,
        "rssi_dbm": None,
        "battery_percent": None,
        "decoder": "rainpoint_tlv",
    }

    try:
        # Ensure raw is a string (handle bytes or other types)
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8', errors='replace')
        raw = str(raw)
        
        # Try ASCII format first: "1,0,1;728(737/705/1),51(54/47/1),C=B601DC05(...)"
        fields, battery_code, rssi_dbm = _parse_ascii_sensor_payload(raw)
        if fields is not None:
            _LOGGER.debug(debug_with_version("HCS0530THO ASCII format: %d fields"), len(fields))
            # Parse fields like "728(737/705/1)" = CO2 with stats
            # and "C=B601DC05(...)" = CO2 related with C= prefix
            co2_raw, _, _ = _parse_stats(fields[0]) if len(fields) > 0 else (None, None, None)
            humidity_raw, _, _ = _parse_stats(fields[1]) if len(fields) > 1 else (None, None, None)
            
            if co2_raw:
                result["co2"] = co2_raw / 10.0  # Raw is CO2*10
            if humidity_raw:
                result["co2humidity"] = humidity_raw
            if rssi_dbm:
                result["rssi_dbm"] = rssi_dbm
            result["decoder"] = "hcs0530tho_ascii"
            return result
        
        # Fall back to hex format: 10#...
        b = _parse_homgar_payload(raw)
        if not b or len(b) < 2:
            return result

        result["rssi_dbm"] = _extract_rssi(b)

        i = 0
        while i < len(b) - 1:
            dp_id = b[i]
            b9 = b[i + 1]
            type_code = (b9 >> 4) & 7

            if dp_id == 207 and i + 3 < len(b):
                co2_raw = int.from_bytes(b[i+2:i+4], 'little')
                co2_ppm = co2_raw / 100.0
                result["co2"] = round(co2_ppm, 1)
                result["co2low"] = round(co2_ppm * 0.9, 1)
                result["co2high"] = round(co2_ppm * 1.1, 1)
                _LOGGER.debug(debug_with_version("CO2: %.1f PPM (DP 207, raw=%d)"), co2_ppm, co2_raw)
                i += 4
                continue
            elif dp_id == 175 and i + 3 < len(b):
                _LOGGER.debug(debug_with_version("Ignoring DP 175 for HCS0530THO (wrong scaling)"))
                i += 4
                continue
            elif dp_id in [185, 220] and b9 == 0x01 and i + 2 < len(b):
                temp_raw = b[i + 2]
                temp_c = temp_raw / 10.0
                if 15 <= temp_c <= 35:
                    result["co2temp"] = round(temp_c, 1)
                    _LOGGER.debug(debug_with_version("Temperature: %.1f°C (DP %d)"), temp_c, dp_id)
                i += 3
                continue
            elif dp_id == 196 and b9 == 0x02 and i + 3 < len(b):
                humidity_raw = b[i + 3]
                if 20 <= humidity_raw <= 80:
                    result["co2humidity"] = humidity_raw
                    _LOGGER.debug(debug_with_version("Humidity: %d%% (DP 196)"), humidity_raw)
                i += 4
                continue
            i += 2

        if result["co2humidity"] is None and len(b) > 21:
            humidity_raw = b[21]
            if 20 <= humidity_raw <= 80:
                result["co2humidity"] = humidity_raw

        result["battery_percent"] = 100
        result["co2batt"] = 100

        try:
            hex_data = raw[3:] if raw.startswith("10#") else raw
            b_exact = bytes.fromhex(hex_data)
            if len(b_exact) >= 30:
                batt_high = b_exact[28]
                batt_low = b_exact[29]
                if batt_high == 0xFF and batt_low == 0x0F:
                    result["battery_percent"] = 100
                    result["co2batt"] = 100
                elif batt_low <= 100:
                    result["battery_percent"] = batt_low
                    result["co2batt"] = batt_low
        except Exception as e:
            _LOGGER.debug(debug_with_version("Battery detection failed: %s"), e)

        try:
            hex_data = raw[3:] if raw.startswith("10#") else raw
            b_exact = bytes.fromhex(hex_data)
            dp_entries = []
            i = 0
            while i < len(b_exact):
                if i + 1 >= len(b_exact):
                    break
                dp_id = b_exact[i]
                type_byte = b_exact[i + 1]
                if type_byte == 0x01 and i + 2 < len(b_exact):
                    dp_entries.append({"dp_id": dp_id, "type": type_byte, "value": b_exact[i + 2]})
                    i += 3
                elif type_byte == 0x02 and i + 3 < len(b_exact):
                    value_int = b_exact[i + 2] + (b_exact[i + 3] << 8)
                    dp_entries.append({"dp_id": dp_id, "type": type_byte, "value": value_int})
                    i += 4
                else:
                    i += 1
                    continue

            humidity_found = False
            for entry in dp_entries:
                dp_id = entry["dp_id"]
                type_byte = entry["type"]
                value = entry["value"]
                if dp_id in [185, 220] and type_byte == 0x01:
                    temp_c = value / 10.0
                    if 15 <= temp_c <= 35 and result.get("co2temp") is None:
                        result["co2temp"] = round(temp_c, 1)
                elif dp_id == 196 and type_byte == 0x02:
                    humidity_raw = (value >> 8) & 0xFF
                    if 20 <= humidity_raw <= 80 and result.get("co2humidity") is None:
                        result["co2humidity"] = humidity_raw
                        humidity_found = True
                elif dp_id == 195 and type_byte == 0x02:
                    humidity_raw = (value >> 8) & 0xFF
                    if 20 <= humidity_raw <= 80 and result.get("co2humidity") is None:
                        result["co2humidity"] = humidity_raw
                        humidity_found = True
                elif dp_id == 191 and type_byte == 0x02:
                    humidity_raw = (value >> 8) & 0xFF
                    if 20 <= humidity_raw <= 80 and result.get("co2humidity") is None:
                        result["co2humidity"] = humidity_raw
                        humidity_found = True
        except Exception as e:
            _LOGGER.debug(debug_with_version("Exact parsing failed, using TLV only: %s"), e)

    except Exception as e:
        _LOGGER.error(
            debug_with_version("Error in HCS0530THO decoder: %s (raw=%r, type=%s)"),
            e, raw, type(raw).__name__
        )
        result["decoder"] = "error"
        result["error"] = str(e)

    return result



def decode_pool_plus(raw: str) -> dict:
    """Decode HCS0530THO (pool plus with CO2) - basic implementation."""
    from ...const import debug_with_version

    _LOGGER.debug(debug_with_version("Decoding HCS0530THO pool plus: %s"), raw)

    result = {
        "type": "co2",
        "device_model": "HCS0530THO",
        "co2": None,
        "temperature_c": None,
        "humidity_percent": None,
        "rssi": None,
        "decoder": "basic",
    }

    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HCS0530THO pool plus decoder: %s"), e)

    return result
