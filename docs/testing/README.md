# Testing Files

This folder contains test scripts and validation tools used during development.

## Files

### Decoder Testing
- `test_hcs014arf.py` - Test HCS014ARF decoder with known payloads from Issue #21
- `test_decoder_simple.py` - Standalone decoder testing without dependencies
- `test_worker_payloads.py` - Test all decoders with real payloads from Cloudflare Worker
- `analyze_payload.py` - Detailed byte-by-byte analysis of HCS014ARF payload
- `analyze_hic801w.py` - Analysis of unknown HIC801W device payload

### MQTT Testing
- `mqtt_test_credentials.py` - Generate MQTT credentials for Alibaba Cloud IoT Platform testing

### API Testing
- `post_with_curl.py` - Test API endpoints with curl

## Usage

These scripts are for development and validation purposes only. They are not part of the integration runtime.

### Running Tests

```bash
# Test HCS014ARF decoder
python3 docs/testing/test_decoder_simple.py

# Test all decoders with worker payloads
python3 docs/testing/test_worker_payloads.py

# Analyze specific payload
python3 docs/testing/analyze_payload.py

# Generate MQTT credentials
python3 docs/testing/mqtt_test_credentials.py
```

## Notes

- Test scripts may require specific Python modules
- Some scripts are standalone and don't require Home Assistant dependencies
- Payloads used in tests are from real user submissions (anonymized)
