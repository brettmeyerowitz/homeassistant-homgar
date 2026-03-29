# Docker Testing Scripts

This directory contains automated testing scripts to ensure the HomGar integration works correctly before releases.

## Pre-commit Docker Testing

### scripts/pre-commit-docker-test.sh

This script runs automatically before any commit that changes `custom_components/` files. It performs the following checks:

#### ✅ Container Status Check
- Verifies Docker container `ha-test` is running
- Exits with error if container not found

#### ✅ Integration Deployment
- Copies updated integration files to Docker container
- Restarts container to load new code
- Waits for container to be ready

#### ✅ Import Error Detection
- Checks for "Setup failed for custom integration 'homgar'" errors
- Checks for "No module named" dependency errors
- Reports specific error details if found

#### ✅ Version Verification
- Confirms the correct version is loaded in Docker
- Verifies `HomGar vX.X.X` appears in container logs
- Ensures staged changes are properly deployed

#### ✅ ASCII Format Testing
- Tests ASCII valve decoder with sample payload
- Tests ASCII sensor decoder with sample payload
- Verifies correct decoder results and zone counts

### Usage

The script runs automatically via Git pre-commit hook. To run manually:

```bash
./scripts/pre-commit-docker-test.sh
```

### Expected Output

```
🔍 Running pre-commit Docker testing...
✅ Docker container 'ha-test' is running
📦 Copying integration to Docker container...
🔄 Restarting Docker container...
⏳ Waiting for container to be ready...
🔍 Checking for import errors...
🔍 Verifying version is loaded...
✅ Version 1.3.14 loaded successfully
🧪 Testing ASCII format decoding...
✅ ASCII format decoding test passed
🧪 Testing sensor ASCII format decoding...
✅ Sensor ASCII format decoding test passed
🎉 All Docker tests passed! Commit allowed.
```

### Bypassing Tests

If absolutely necessary (not recommended), bypass with:

```bash
git commit --no-verify
```

### Prerequisites

1. Docker container named `ha-test` must be running
2. Container must have Home Assistant installed
3. Container must be accessible via `docker exec`

### Troubleshooting

#### Container not running
```bash
docker start ha-test
```

#### Permission denied
```bash
chmod +x scripts/pre-commit-docker-test.sh
```

#### Script not found
Ensure the script exists at `scripts/pre-commit-docker-test.sh`

## Integration with Git Hooks

The pre-commit hook (`.git/hooks/pre-commit`) automatically:
1. Runs version bump check
2. Runs Docker testing (if script exists)
3. Blocks commit if any test fails
4. Provides clear error messages

This ensures every code change is tested in a real Home Assistant environment before being committed! 🎯
