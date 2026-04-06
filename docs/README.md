# Documentation

This folder contains all documentation for the HomGar/RainPoint integration.

## Structure

### Main Documentation
- `cloudflare_worker.md` - Complete Cloudflare Worker documentation
- `project_reference.md` - Comprehensive project reference guide
- `payload_validation_v2.0.1.md` - Payload validation results for v2.0.1
- `dean_valve_issue_analysis.md` - Analysis of Issue #11 (valve state detection)

### Subdirectories

#### `/testing/`
Test scripts and validation tools used during development:
- Decoder testing scripts
- MQTT credential generators
- Payload analysis tools
- API testing utilities

#### `/old_releases/`
Archived release notes and documentation from previous versions:
- Historical release notes (v1.3.x series)
- Old debugging documentation
- Publishing guides

## File Organization Guidelines

### Root Directory Files
The root directory should only contain:
- `README.md` - Main integration documentation
- `CHANGELOG.md` - Version history
- `LICENSE` - License file
- `commit_message.txt` - Temporary file for current release (deleted after commit)
- `release_notes_vX.X.X.md` - Temporary file for current release (deleted after release)

### Where to Put Files

**Test Scripts** → `docs/testing/`
- Python test files
- Validation scripts
- Analysis tools

**Old Release Files** → `docs/old_releases/`
- Previous release notes
- Historical documentation
- Archived guides

**Active Documentation** → `docs/`
- Project reference guides
- Technical documentation
- Analysis documents

**Integration Code** → `custom_components/homgar/`
- Python modules
- Integration logic
- API clients and decoders

## Workflow

### During Development
1. Create test scripts in `docs/testing/`
2. Document findings in `docs/`
3. Keep root directory clean

### During Release
1. Create `commit_message.txt` in root
2. Create `release_notes_vX.X.X.md` in root
3. After release, delete temporary files
4. Archive old release notes to `docs/old_releases/`

### After Release
1. Clean up root directory
2. Move test files to `docs/testing/`
3. Update documentation in `docs/`

## Important Notes

- **Never commit test files to root directory**
- **Always clean up temporary files after release**
- **Keep root directory minimal and organized**
- **Document all major changes in appropriate docs/ files**
