"""
Decoder functions for HomGar API.

This module contains all device-specific decoder functions for different
HomGar and RainPoint device types.
"""

import logging

from .utils import _parse_homgar_payload, _parse_tlv_payload, _le16, _f10_to_c, _base_decoder_dict
from .validators import _validate_payload, _validate_tag, _extract_rssi, _extract_status_code, _battery_status_to_percent

_LOGGER = logging.getLogger(__name__)


def decode_htv213frf_valve(raw: str) -> dict:
    """
    Decode HTV213FRF/HTV245FRF valve hub payload.
    
    These devices support two formats:
    1. Hex format (11#...) - uses custom TLV structure
    2. ASCII format (1,-84,1;...) - uses comma-separated values
    """
    try:
        # Check payload format and route to appropriate decoder
        if raw.startswith("11#"):
            return _decode_htv213frf_hex(raw)
        elif "," in raw and (";" in raw or "|" in raw):
            return _decode_htv213frf_ascii(raw)
        else:
            raise ValueError(f"Unexpected payload format: {raw}")
            
    except Exception as e:
        _LOGGER.error("HTV213FRF decoder error: %s", e)
        return {
            "type": "valve_hub",
            "rssi_dbm": 0,
            "raw_bytes": [],
            "zones": {},
            "tlv_raw": {},
            "decoder": "htv213frf_error",
            "error": str(e)
        }


def _decode_htv213frf_ascii(raw: str) -> dict:
    """
    Decode HTV213FRF ASCII format payload.
    
    Format: 1,-84,1;0,149,0,0,0,0|0,6,0,0,0,0
    Structure: [flags],[rssi],[flags];[zone1_data]|[zone2_data]
    """
    from ..const import debug_with_version
    
    _LOGGER.info(debug_with_version("HTV213FRF ASCII payload: %s"), raw)
    
    zones = {}
    hub_online = False
    
    try:
        # Parse the ASCII format
        # Example: 1,-84,1;0,149,0,0,0,0|0,6,0,0,0,0
        
        # Split on semicolon to separate header from zone data
        if ";" not in raw:
            raise ValueError("Invalid ASCII format: missing semicolon")
            
        header_part, zone_part = raw.split(";", 1)
        
        # Parse header: 1,-84,1
        header_parts = header_part.split(",")
        if len(header_parts) < 3:
            raise ValueError("Invalid ASCII header format")
            
        flags1 = int(header_parts[0])
        rssi_raw = int(header_parts[1])  # RSSI in dBm (negative number)
        flags2 = int(header_parts[2])
        
        # Extract RSSI (convert from negative to positive dBm)
        rssi_dbm = rssi_raw if rssi_raw < 0 else 0
        
        # Parse zone data: 0,149,0,0,0,0|0,6,0,0,0,0
        zone_sections = zone_part.split("|")
        zone_mapping = {}
        sequential_zone = 1
        
        for zone_data in zone_sections:
            if not zone_data.strip():
                continue
                
            zone_parts = zone_data.split(",")
            if len(zone_parts) < 6:
                _LOGGER.warning("Invalid zone data format: %s", zone_data)
                continue
            
            # Parse zone data: [zone_id?, state, duration?, ?, ?, ?]
            # Based on observed patterns:
            # Zone 1: 0,149,0,0,0,0
            # Zone 2: 0,6,0,0,0,0
            
            zone_id_raw = int(zone_parts[0])
            state = int(zone_parts[1])
            duration = int(zone_parts[2]) if len(zone_parts) > 2 else 0
            
            # Map to sequential zone number
            zone_mapping[sequential_zone] = {
                'raw_zone_id': zone_id_raw,
                'open': state != 0x00,
                'duration_seconds': duration,
                'raw_ascii_data': zone_data
            }
            
            _LOGGER.info("HTV213FRF ASCII Zone %d (raw ID %d): state=%d, duration=%d", 
                        sequential_zone, zone_id_raw, state, duration)
            sequential_zone += 1
        
        zones = zone_mapping
        
        # For ASCII format, assume hub is online if we got valid data
        hub_online = True
        _LOGGER.info("HTV213FRF ASCII hub state: online (valid ASCII data received)")
        
        result = {
            "type": "valve_hub",
            "rssi_dbm": rssi_dbm,
            "raw_bytes": raw.encode('ascii'),
            "zones": zones,
            "tlv_raw": {},
            "hub_online": hub_online,
            "hub_state_raw": "ascii_format",
            "decoder": "htv213frf_ascii",
            "debug_info": {
                "payload_format": "ascii",
                "raw_payload": raw,
                "header_parts": header_parts,
                "zone_sections": zone_sections,
                "zones_found": len(zones),
                "rssi_raw": rssi_raw
            }
        }
        
        _LOGGER.info(debug_with_version("HTV213FRF ASCII decoded: %d zones, hub_online=%s, rssi=%d"), 
                   len(zones), hub_online, rssi_dbm)
        return result
        
    except Exception as e:
        _LOGGER.error("HTV213FRF ASCII decoder error: %s", e)
        raise


def _decode_htv213frf_hex(raw: str) -> dict:
    """
    Decode HTV213FRF hex format payload.
    
    Format: 11#17E1CE0019D8001AD8001D201E2021B700000000...
    Uses custom TLV structure with fixed-length records.
    """
    from ..const import debug_with_version
    
    try:
        b = _parse_homgar_payload(raw)
        _LOGGER.debug(debug_with_version("HTV213FRF hex raw bytes: %s"), b)
        
        zones = {}
        
        # Try to parse as standard TLV first (for debugging)
        try:
            tlv = _parse_tlv_payload(raw)
            _LOGGER.info(debug_with_version("HTV213FRF TLV entries: %s"), {
                f"0x{dp:02X}": (f"0x{type_byte:02X}", f"0x{value_int:02X}" if value_int < 256 else value_int, raw_bytes.hex())
                for dp, (type_byte, value_int, raw_bytes) in tlv.items()
            })
        except Exception as e:
            _LOGGER.info(debug_with_version("HTV213FRF TLV parsing failed: %s"), e)
            tlv = {}
        
        # If standard TLV worked, use it
        if tlv:
            return decode_valve_hub(raw)
        
        # Custom HTV213FRF parsing based on observed patterns
        # The payload seems to use fixed-length records:
        # [zone_id][state][0x00][duration_high][duration_low][0x00][0x00]
        
        # Look for zone patterns in the raw bytes
        # Based on the user's payload, zones appear to start at specific positions
        if len(b) >= 20:  # Minimum length for zone data
            # Try to extract zones from the pattern
            # Zone 1: bytes 4-9 (19 D8 00 1A D8 00)
            # Zone 2: bytes 10-15 (1D 20 1E 20 21 B7) - this looks different
            
            # Let's try a different approach - look for repeated patterns
            # The pattern seems to be: [zone_id][state][0x00][duration][0x00][0x00]
            
            zone_data = []
            # Scan through bytes looking for potential zone patterns
            i = 4  # Start after the header
            while i < len(b) - 6:
                zone_id = b[i]
                state = b[i + 1]
                if b[i + 2] == 0x00 and b[i + 5] == 0x00:  # Pattern match
                    duration = (b[i + 3] << 8) | b[i + 4]
                    zone_data.append({
                        'zone_id': zone_id,
                        'state': state,
                        'duration': duration,
                        'position': i
                    })
                    _LOGGER.debug("Found potential zone %d: state=%d, duration=%d", zone_id, state, duration)
                    i += 6
                else:
                    i += 1
            
            # Convert zone data to expected format
            # Map raw zone IDs to sequential zone numbers
            zone_mapping = {}
            sequential_zone = 1
            
            for zone in zone_data:
                zone_num = sequential_zone  # Use sequential numbering
                zone_mapping[sequential_zone] = {
                    'raw_zone_id': zone['zone_id'],
                    'open': zone['state'] != 0x00,
                    'duration_seconds': zone['duration'],
                    'raw_position': zone['position']
                }
                _LOGGER.info("HTV213FRF Zone %d (raw ID %d): state=%d, duration=%d, position=%d", 
                           sequential_zone, zone['zone_id'], zone['state'], zone['duration'], zone['position'])
                sequential_zone += 1
            
            zones = zone_mapping
        
        # Extract hub online state (looking for 0x18 pattern)
        hub_online = False
        _LOGGER.info(debug_with_version("HTV213FRF checking hub state - len(b)=%d, b[26]=0x%02X, b[27]=0x%02X"), 
                     len(b), b[26] if len(b) > 26 else None, b[27] if len(b) > 27 else None)
        
        if len(b) >= 28 and b[26] == 0x18:
            # Standard pattern: 0x18 at position 26
            # For HTV213FRF, position 27 might use different values than 0x01
            # Let's try multiple possibilities for "online"
            if b[27] == 0x01:
                hub_online = True
                _LOGGER.info("Hub state (0x18 pattern, 0x01): %s (byte 27: 0x%02X)", hub_online, b[27])
            elif b[27] == 0xDC:
                # Based on user's payload, 0xDC might mean online for HTV213FRF
                hub_online = True
                _LOGGER.info("Hub state (0x18 pattern, 0xDC): %s (byte 27: 0x%02X)", hub_online, b[27])
            else:
                hub_online = False
                _LOGGER.info("Hub state (0x18 pattern, other): %s (byte 27: 0x%02X)", hub_online, b[27])
        else:
            _LOGGER.warning("HTV213FRF: Could not determine hub state from payload")
        
        result = {
            "type": "valve_hub",
            "rssi_dbm": _extract_rssi(b) if len(b) > 1 else 0,
            "raw_bytes": b,
            "zones": zones,
            "tlv_raw": tlv,
            "hub_online": hub_online,
            "hub_state_raw": b[27] if len(b) > 27 else None,
            "decoder": "htv213frf_custom",
            "debug_info": {
                "payload_length": len(b),
                "hex_payload": raw,
                "tlv_entries": len(tlv),
                "zones_found": len(zones),
                "zone_data": zone_data if 'zone_data' in locals() else []
            }
        }
        
        _LOGGER.debug(debug_with_version("HTV213FRF decoded: %d zones, hub_online=%s"), len(zones), hub_online)
        return result
        
    except Exception as e:
        _LOGGER.error("HTV213FRF decoder error: %s", e)
        return {
            "type": "valve_hub",
            "rssi_dbm": 0,
            "raw_bytes": [],
            "zones": {},
            "tlv_raw": {},
            "decoder": "htv213frf_error",
            "error": str(e)
        }


def decode_moisture_full(raw: str) -> dict:
    """
    Decode HCS021FRF (moisture + temp + lux).
    
    Supports two formats:
    1. Hex format (10#...) - standard TLV structure
    2. ASCII format (1,-73,1;694,70,G=292478) - comma-separated values
    """
    try:
        # Check payload format and route to appropriate decoder
        if raw.startswith("10#"):
            return _decode_moisture_full_hex(raw)
        elif "," in raw and (";" in raw or "=" in raw):
            return _decode_moisture_full_ascii(raw)
        else:
            raise ValueError(f"Unexpected payload format: {raw}")
            
    except Exception as e:
        _LOGGER.error("HCS021FRF decoder error: %s", e)
        return {
            "type": "moisture_full",
            "rssi_dbm": 0,
            "raw_bytes": [],
            "decoder": "hcs021frf_error",
            "error": str(e)
        }


def _decode_moisture_full_ascii(raw: str) -> dict:
    """
    Decode HCS021FRF ASCII format payload.
    
    Format: 1,-73,1;694,70,G=292478
    Structure: [flags],[rssi],[flags];[temp_raw],[moisture],[lux_data]
    """
    from ..const import debug_with_version
    
    _LOGGER.info(debug_with_version("HCS021FRF ASCII payload: %s"), raw)
    
    try:
        # Parse the ASCII format
        # Example: 1,-73,1;694,70,G=292478
        
        # Split on semicolon to separate header from sensor data
        if ";" not in raw:
            raise ValueError("Invalid ASCII format: missing semicolon")
            
        header_part, sensor_part = raw.split(";", 1)
        
        # Parse header: 1,-73,1
        header_parts = header_part.split(",")
        if len(header_parts) < 3:
            raise ValueError("Invalid ASCII header format")
            
        flags1 = int(header_parts[0])
        rssi_raw = int(header_parts[1])  # RSSI in dBm (negative number)
        flags2 = int(header_parts[2])
        
        # Extract RSSI (convert from negative to positive dBm)
        rssi_dbm = rssi_raw if rssi_raw < 0 else 0
        
        # Parse sensor data: 694,70,G=292478
        sensor_parts = sensor_part.split(",")
        
        if len(sensor_parts) < 3:
            raise ValueError("Invalid ASCII sensor data format")
        
        # Parse sensor values
        temp_raw = int(sensor_parts[0])  # Temperature raw value
        moisture = int(sensor_parts[1])   # Moisture percentage
        lux_data = sensor_parts[2]        # Lux data (may contain =)
        
        # Parse temperature - convert from raw to Celsius
        # Based on hex format: temp_raw_f10, so divide by 10
        temp_c = temp_raw / 10.0 if temp_raw else 0
        
        # Parse lux data if it contains = (e.g., "G=292478")
        if "=" in lux_data:
            lux_parts = lux_data.split("=")
            if len(lux_parts) == 2:
                lux_raw = int(lux_parts[1])
                lux = lux_raw / 10.0  # Assuming similar scaling as hex format
            else:
                lux = 0
        else:
            # Try to parse as direct lux value
            try:
                lux = int(lux_data) / 10.0
            except ValueError:
                lux = 0
        
        result = {
            "type": "moisture_full",
            "rssi_dbm": rssi_dbm,
            "raw_bytes": raw.encode('ascii'),
            "moisture_percent": moisture,
            "temperature_c": temp_c,
            "temperature_f10": temp_raw,
            "illuminance_lux": lux,
            "illuminance_raw10": int(lux * 10) if lux else 0,
            "decoder": "hcs021frf_ascii",
            "debug_info": {
                "payload_format": "ascii",
                "raw_payload": raw,
                "header_parts": header_parts,
                "sensor_parts": sensor_parts,
                "rssi_raw": rssi_raw,
                "lux_data_parsed": lux_data
            }
        }
        
        _LOGGER.info(debug_with_version("HCS021FRF ASCII decoded: temp=%.1f°C, moisture=%d%%, lux=%.1f, rssi=%d"), 
                   temp_c, moisture, lux, rssi_dbm)
        return result
        
    except Exception as e:
        _LOGGER.error("HCS021FRF ASCII decoder error: %s", e)
        raise


def _decode_moisture_full_hex(raw: str) -> dict:
    """
    Decode HCS021FRF hex format payload.
    
    Layout after '10#':
    b0 = 0xE1
    b1 = RSSI (signed)
    b2 = 0x00
    b3 = 0xDC
    b4 = 0x01
    b5 = 0x85
    b6,b7 = temp_raw F*10 LE
    b8     = 0x88  (moisture tag)
    b9     = moisture %
    b10    = 0xC6  (lux tag)
    b11,b12= lux_raw * 10 LE
    b13    = 0x00
    b14,b15= 0xFF,0x0F (status/battery)
    
    Based on actual payload: 10#E1A200DC0185AB02881FC6600600FF0FFA28F718
    E1 A2 00 DC 01 85 AB 02 88 1F C6 60 06 00 FF 0F FA 28 F7 18
    b[1]=0xA2=162-256=-94 RSSI
    b[6:7]=0x02AB=683°F*10 → 68.3°F → 20.2°C
    b[9]=0x1F=31% moisture
    b[11:12]=0x0660=1632 lux*10 → 163.2 lux
    
    Note: Some payloads are 20 bytes instead of 16
    """
    # Handle both 16-byte and 20-byte payloads
    b = _validate_payload(raw, 16)  # Minimum 16 bytes
    if len(b) > 20:
        raise ValueError(f"HCS021FRF payload too long: {len(b)} bytes")
    
    _validate_tag(b, 5, 0x85, "HCS021FRF")
    
    rssi = _extract_rssi(b)
    temp_raw_f10 = _le16(b, 6)
    temp_c = _f10_to_c(temp_raw_f10)

    _validate_tag(b, 8, 0x88, "HCS021FRF")
    moisture = b[9]

    _validate_tag(b, 10, 0xC6, "HCS021FRF")
    lux_raw10 = _le16(b, 11)
    lux = lux_raw10 / 10.0

    # Status code is at different positions depending on payload length
    if len(b) >= 16:
        status_code = _extract_status_code(b, 14, 15)
    else:
        status_code = 0  # Default if not available

    result = _base_decoder_dict("moisture_full", rssi, b)
    result.update({
        "moisture_percent": moisture,
        "temperature_c": temp_c,
        "temperature_f10": temp_raw_f10,
        "illuminance_lux": lux,
        "illuminance_raw10": lux_raw10,
        "battery_status_code": status_code,
        "battery_percent": _battery_status_to_percent(status_code),
        "decoder": "hcs021frf_hex",
    })
    return result


def decode_hws019wrf_v2(raw: str) -> dict:
    """
    Decode HWS019WRF-V2 (Display Hub) CSV/semicolon payload.
    Example: '1,0,1;788(788/777/1),68(68/64/1),P=9685(9684/9684/1),'
    """
    _LOGGER.debug("decode_hws019wrf_v2 called with raw: %r", raw)
    try:
        parts = raw.split(';')
        # First part: status flags (e.g., '1,0,1')
        flags = [int(x) for x in parts[0].split(',') if x.strip().isdigit()]
        readings = {}
        if len(parts) > 1:
            for item in parts[1].split(','):
                item = item.strip()
                if not item:
                    continue
                if '(' in item:
                    key, val = item.split('(', 1)
                    readings[key.strip()] = val.strip(')')
                elif '=' in item:
                    key, val = item.split('=', 1)
                    readings[key.strip()] = val.strip()
        result = {
            "type": "hws019wrf_v2",
            "flags": flags,
            "readings": readings,
            "raw": raw,
        }
        _LOGGER.debug("decode_hws019wrf_v2 result: %r", result)
        return result
    except Exception as ex:
        _LOGGER.warning("Failed to decode HWS019WRF-V2 payload: %s (raw: %r)", ex, raw)
        return {"type": "hws019wrf_v2", "raw": raw, "error": str(ex)}


def decode_valve_hub(raw: str) -> dict:
    """
    Decode an irrigation valve hub TLV payload (e.g. HTV0540FRF).

    Confirmed DP map (derived from live payload capture):
    - Zone N state DP   = _DP_HUB_STATE + N  (0x19 = zone 1, 0x1A = zone 2, ...)
    - Zone N duration DP = _DP_BASE_DURATION + N (0x25 = zone 1, 0x26 = zone 2, ...)
    """
    from ..const import debug_with_version
    
    # DP IDs for valve hub zone state and duration (confirmed via payload capture)
    _DP_HUB_STATE = 0x18
    _DP_BASE_DURATION = 0x24  # zone N duration DP = 0x24 + N

    try:
        b = _parse_homgar_payload(raw)
        _LOGGER.debug(debug_with_version("Valve hub raw bytes: %s"), b)
        
        tlv = _parse_tlv_payload(raw)
        _LOGGER.debug(debug_with_version("Valve hub TLV entries: %s"), {
            f"0x{dp:02X}": (f"0x{type_byte:02X}", f"0x{value_int:02X}" if value_int < 256 else value_int, raw_bytes.hex())
            for dp, (type_byte, value_int, raw_bytes) in tlv.items()
        })

        zones = {}
        hub_online = False

        # Extract hub online state from DP 0x18
        if _DP_HUB_STATE in tlv:
            _, hub_state_raw, _ = tlv[_DP_HUB_STATE]
            hub_online = hub_state_raw == 0x01
            _LOGGER.info(debug_with_version("Valve hub state: %s (raw: 0x%02X)"), hub_online, hub_state_raw)

        # Extract zone states and durations
        for zone_num in range(1, 9):  # Support up to 8 zones
            state_dp = _DP_HUB_STATE + zone_num
            duration_dp = _DP_BASE_DURATION + zone_num

            zone_state = None
            zone_duration = 0

            if state_dp in tlv:
                _, state_raw, _ = tlv[state_dp]
                zone_state = state_raw == 0x01

            if duration_dp in tlv:
                _, duration_raw, _ = tlv[duration_dp]
                # Duration appears to be in seconds (little-endian)
                zone_duration = duration_raw

            if zone_state is not None:
                zones[zone_num] = {
                    "open": zone_state,
                    "duration_seconds": zone_duration,
                    "state_raw": state_raw if state_dp in tlv else None,
                    "duration_raw": duration_raw if duration_dp in tlv else None,
                }

        result = {
            "type": "valve_hub",
            "rssi_dbm": _extract_rssi(b) if len(b) > 1 else 0,
            "raw_bytes": b,
            "zones": zones,
            "tlv_raw": tlv,
            "hub_online": hub_online,
            "hub_state_raw": tlv.get(_DP_HUB_STATE, (None, None, None))[1],
            "decoder": "valve_hub_tlv",
        }
        
        _LOGGER.info(debug_with_version("Valve hub decoded: %d zones, hub_online=%s"), len(zones), hub_online)
        return result

    except Exception as e:
        _LOGGER.error("Valve hub decoder error: %s", e)
        return {
            "type": "valve_hub",
            "rssi_dbm": 0,
            "raw_bytes": [],
            "zones": {},
            "tlv_raw": {},
            "decoder": "valve_hub_error",
            "error": str(e)
        }


def decode_rain(raw: str) -> dict:
    """
    Decode HCS012ARF (rain gauge).
    Layout after '10#':
    b0 = 0xE1
    b1 = 0x00 (seems constant in your samples)
    b2 = 0x00
    b3,4 = FD,04 ; b5,b6 = lastHour raw*10 LE
    b7,8 = FD,05 ; b9,b10 = last24h raw*10 LE
    b11,12 = FD,06 ; b13,b14 = last7d raw*10 LE
    b15,16 = DC,01
    b17 = 0x97 ; b18,b19 = total raw*10 LE
    b20,b21 = 0x00,0x00
    b22,b23 = 0xFF,0x0F (status/battery)
    b24..b27 = tail
    
    Based on actual payload: 10#E10000FD040000FD054E07FD064E07DC01974E070000FF0F0410F718
    E1 00 00 FD 04 00 00 FD 05 4E 07 FD 06 4E 07 DC 01 97 4E 07 00 00 FF 0F 04 10 F7 18
    b[5:6]=0x0000=0.0mm last hour
    b[9:10]=0x074E=1870mm*10 → 187.0mm last 24h
    b[13:14]=0x074E=1870mm*10 → 187.0mm last 7d
    b[18:19]=0x074E=1870mm*10 → 187.0mm total
    """
    b = _validate_payload(raw, 24)

    # Validate rain-specific tags
    if not (b[3] == 0xFD and b[4] == 0x04):
        raise ValueError("HCS012ARF: Missing FD 04 at [3:5]")
    if not (b[7] == 0xFD and b[8] == 0x05):
        raise ValueError("HCS012ARF: Missing FD 05 at [7:9]")
    if not (b[11] == 0xFD and b[12] == 0x06):
        raise ValueError("HCS012ARF: Missing FD 06 at [11:13]")
    _validate_tag(b, 17, 0x97, "HCS012ARF")

    last_hour_raw10 = _le16(b, 5)
    last_24h_raw10 = _le16(b, 9)
    last_7d_raw10 = _le16(b, 13)
    total_raw10 = _le16(b, 18)

    status_code = _extract_status_code(b, 22, 23)

    result = _base_decoder_dict("rain", 0, b)  # Rain gauge doesn't have RSSI in standard position
    result.update({
        "rain_last_hour_mm": last_hour_raw10 / 10.0,
        "rain_last_24h_mm": last_24h_raw10 / 10.0,
        "rain_last_7d_mm": last_7d_raw10 / 10.0,
        "rain_total_mm": total_raw10 / 10.0,
        "rain_last_hour_raw10": last_hour_raw10,
        "rain_last_24h_raw10": last_24h_raw10,
        "rain_last_7d_raw10": last_7d_raw10,
        "rain_total_raw10": total_raw10,
        "battery_status_code": status_code,
        "battery_percent": _battery_status_to_percent(status_code),
    })
    return result


def decode_moisture_simple(raw: str) -> dict:
    """
    Decode HCS026FRF (moisture-only) payload.
    Layout after '10#':
    b0 = 0xE1
    b1 = RSSI (signed int8)
    b2 = 0x00
    b3 = 0xDC
    b4 = 0x01
    b5 = 0x88  (moisture tag)
    b6 = moisture % (0-100)
    b7,b8 = status/battery field
    
    Based on actual payload: 10#E1C600DC01881AFF0F5E21F718
    E1 C6 00 DC 01 88 1A FF 0F 5E 21 F7 18
    b[1]=0xC6=198-256=-58 RSSI
    b[6]=0x1A=26% moisture
    """
    b = _validate_payload(raw, 9)
    _validate_tag(b, 5, 0x88, "HCS026FRF")
    
    rssi = _extract_rssi(b)
    moisture = b[6]
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("moisture_simple", rssi, b)
    result.update({
        "moisture_percent": moisture,
        "battery_status_code": status_code,
        "battery_percent": _battery_status_to_percent(status_code),
    })
    return result


def decode_flow_meter(raw: str) -> dict:
    """Decode HCS008FRF (flow meter)."""
    from ..const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding HCS008FRF: %s"), raw)
    
    result = {
        "type": "flowmeter",
        "device_model": "HCS008FRF",
        "flowcurrentused": None,
        "flowcurrenduration": None,
        "flowtoday": None,
        "flowtotal": None,
        "flowbatt": None,
        "rssi": None,
        "decoder": "basic",
    }
    
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
        
        # Basic flow parsing - can be enhanced with exact RainPoint logic later
        _LOGGER.debug(debug_with_version("HCS008FRF basic parsing completed"))
        
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HCS008FRF decoder: %s"), e)
    
    return result


# Alias for backward compatibility
decode_flowmeter = decode_flow_meter


def decode_pool_plus(raw: str) -> dict:
    """Decode HCS0530THO (pool plus with CO2)."""
    from ..const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding HCS0530THO: %s"), raw)
    
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
        
        # Basic CO2 parsing - can be enhanced with exact RainPoint logic later
        _LOGGER.debug(debug_with_version("HCS0530THO basic parsing completed"))
        
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HCS0530THO decoder: %s"), e)
    
    return result


def decode_soil(raw: str) -> dict:
    """Decode soil sensor."""
    from ..const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding soil sensor: %s"), raw)
    
    result = {
        "type": "soil",
        "rssi": None,
        "decoder": "basic",
    }
    
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
        
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in soil decoder: %s"), e)
    
    return result


def decode_temp_hum(raw: str) -> dict:
    """Decode temperature/humidity sensor."""
    from ..const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding temp/hum sensor: %s"), raw)
    
    result = {
        "type": "temphum",
        "rssi": None,
        "decoder": "basic",
    }
    
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
        
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in temp/hum decoder: %s"), e)
    
    return result


def decode_temp_hum_full(raw: str) -> dict:
    """Decode full temperature/humidity sensor."""
    from ..const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding full temp/hum sensor: %s"), raw)
    
    result = {
        "type": "temphum_full",
        "rssi": None,
        "decoder": "basic",
    }
    
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
        
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in full temp/hum decoder: %s"), e)
    
    return result


def decode_co2(raw: str) -> dict:
    """Decode CO2 sensor."""
    from ..const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding CO2 sensor: %s"), raw)
    
    result = {
        "type": "co2",
        "rssi": None,
        "decoder": "basic",
    }
    
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
        
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in CO2 decoder: %s"), e)
    
    return result


def decode_display(raw: str) -> dict:
    """Decode display sensor."""
    from ..const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding display sensor: %s"), raw)
    
    result = {
        "type": "display",
        "rssi": None,
        "decoder": "basic",
    }
    
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
        
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in display decoder: %s"), e)
    
    return result


def decode_unknown(raw: str) -> dict:
    """Decode unknown device."""
    from ..const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding unknown device: %s"), raw)
    
    result = {
        "type": "unknown",
        "rssi": None,
        "decoder": "basic",
    }
    
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
        
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in unknown decoder: %s"), e)
    
    return result


# Additional HCS decoders - basic implementations
def decode_temphum(raw: str) -> dict:
    """Decode HCS014ARF (temperature/humidity) payload."""
    from ..const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding HCS014ARF: %s"), raw)
    
    result = {
        "type": "temphum",
        "rssi": None,
        "decoder": "basic",
    }
    
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
        
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HCS014ARF decoder: %s"), e)
    
    return result


def decode_pool(raw: str) -> dict:
    """Decode HCS0528ARF (pool/temperature) payload."""
    from ..const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding HCS0528ARF: %s"), raw)
    
    result = {
        "type": "pool",
        "rssi": None,
        "decoder": "basic",
    }
    
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
        
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HCS0528ARF decoder: %s"), e)
    
    return result


# HCS variant decoders - basic implementations
def decode_hcs005frf(raw: str) -> dict:
    """Decode HCS005FRF (moisture-only sensor)."""
    return decode_moisture_simple(raw)


def decode_hcs003frf(raw: str) -> dict:
    """Decode HCS003FRF (moisture-only sensor)."""
    return decode_moisture_simple(raw)


def decode_hcs024frf_v1(raw: str) -> dict:
    """Decode HCS024FRF-V1 (multi-sensor)."""
    return decode_moisture_full(raw)


def decode_hcs014arf(raw: str) -> dict:
    """Decode HCS014ARF (Temperature/Humidity)."""
    return decode_temphum(raw)


def decode_hcs015arf(raw: str) -> dict:
    """Decode HCS015ARF (pool temperature sensor)."""
    return decode_pool(raw)


def decode_hcs0528arf(raw: str) -> dict:
    """Decode HCS0528ARF (pool temperature sensor)."""
    return decode_pool(raw)


# Additional HCS variant decoders - placeholder implementations
def decode_hcs027arf(raw: str) -> dict:
    """Decode HCS027ARF (unknown sensor type)."""
    return decode_unknown(raw)


def decode_hcs016arf(raw: str) -> dict:
    """Decode HCS016ARF (unknown sensor type)."""
    return decode_unknown(raw)


def decode_hcs044frf(raw: str) -> dict:
    """Decode HCS044FRF (unknown sensor type)."""
    return decode_unknown(raw)


def decode_hcs666frf(raw: str) -> dict:
    """Decode HCS666FRF (unknown sensor variant)."""
    return decode_unknown(raw)


def decode_hcs666rfr_p(raw: str) -> dict:
    """Decode HCS666RFR-P (unknown sensor variant)."""
    return decode_unknown(raw)


def decode_hcs999frf(raw: str) -> dict:
    """Decode HCS999FRF (unknown sensor variant)."""
    return decode_unknown(raw)


def decode_hcs999frf_p(raw: str) -> dict:
    """Decode HCS999FRF-P (unknown sensor variant)."""
    return decode_unknown(raw)


def decode_hcs666frf_x(raw: str) -> dict:
    """Decode HCS666FRF-X (unknown sensor variant)."""
    return decode_unknown(raw)


def decode_hcs701b(raw: str) -> dict:
    """Decode HCS701B (unknown sensor type)."""
    return decode_unknown(raw)


def decode_hcs596wb(raw: str) -> dict:
    """Decode HCS596WB (unknown sensor type)."""
    return decode_unknown(raw)


def decode_hcs596wb_v4(raw: str) -> dict:
    """Decode HCS596WB-V4 (unknown sensor type)."""
    return decode_unknown(raw)


def decode_hcs706arf(raw: str) -> dict:
    """Decode HCS706ARF (unknown sensor type)."""
    return decode_unknown(raw)


def decode_hcs802arf(raw: str) -> dict:
    """Decode HCS802ARF (unknown sensor type)."""
    return decode_unknown(raw)


def decode_hcs048b(raw: str) -> dict:
    """Decode HCS048B (unknown sensor type)."""
    return decode_unknown(raw)


def decode_hcs888arf_v1(raw: str) -> dict:
    """Decode HCS888ARF-V1 (unknown sensor type)."""
    return decode_unknown(raw)


def decode_hcs0600arf(raw: str) -> dict:
    """Decode HCS0600ARF (unknown sensor type)."""
    return decode_unknown(raw)
