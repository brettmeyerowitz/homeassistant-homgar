# Version Enforcement

This repository has automated checks to ensure the manifest version is properly bumped when custom components are modified.

## GitHub Actions Check

**File:** `.github/workflows/check-version.yml`

**Triggers:**
- Push to main/master branch
- Pull requests to main/master

**Behavior:**
- Checks if any files in `custom_components/` were changed
- If changed, verifies that `custom_components/homgar/manifest.json` version was bumped
- Blocks the commit/PR if version wasn't updated
- Provides helpful error message with suggested version bump

**Example Error:**
```
❌ ERROR: Manifest version not bumped!
custom_components/ files changed but version remained 1.3.5

Please bump the version in custom_components/homgar/manifest.json
Example: 1.3.5 -> 1.3.6
```

## Pre-commit Hook (Local Development)

**File:** `.git/hooks/pre-commit`

**Behavior:**
- Runs automatically before each commit
- Checks staged changes for custom_components modifications
- Prevents local commits if version isn't bumped
- Provides immediate feedback during development

**Usage:**
```bash
# Normal commit (will check version)
git commit -m "Add new sensor feature"

# Bypass check (not recommended)
git commit --no-verify -m "Add new sensor feature"
```

## Version Bumping Guidelines

### When to Bump Version
- **Patch (1.3.5 → 1.3.6):** Bug fixes, small improvements, valve decoder fixes
- **Minor (1.3.5 → 1.4.0):** New features, new device support, breaking changes to config
- **Major (1.3.5 → 2.0.0):** Major architectural changes, breaking API changes

### How to Bump Version
1. Edit `custom_components/homgar/manifest.json`
2. Update the `version` field
3. Update `CHANGELOG.md` with changes
4. Commit and push

### Version Format
- Semantic versioning: `MAJOR.MINOR.PATCH`
- Always increment by 1 for the appropriate level
- No leading zeros (use `1.3.6`, not `1.3.06`)

## Troubleshooting

### Check Failed But Version Shouldn't Change
If you made documentation-only changes or other non-code changes:
```bash
git commit --no-verify -m "Update README"
```

### Hook Not Working
Make sure the pre-commit hook is executable:
```bash
chmod +x .git/hooks/pre-commit
```

### GitHub Actions Failed
The GitHub Actions check is just a safety net - if it fails, you can:
1. Update the version locally
2. Push the version bump
3. The next push will succeed

## Benefits

1. **Consistent Releases:** Never forget to bump version for releases
2. **Clear History:** Each version change corresponds to actual code changes
3. **Automated Safety:** Both local and remote protection against version mistakes
4. **Developer Experience:** Immediate feedback during development
