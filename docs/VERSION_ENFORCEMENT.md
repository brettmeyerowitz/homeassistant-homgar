# Version Enforcement

This repository has automated checks to ensure the manifest version is properly bumped when custom components are modified, and that release tags match the manifest version.

## GitHub Actions Checks

### Commit/PR Check
**File:** `.github/workflows/check-version.yml`

**Triggers:**
- Push to main/master branch
- Pull requests to main/master

**Behavior:**
- Checks if any files in `custom_components/` were changed
- If changed, verifies that `custom_components/homgar/manifest.json` version was bumped
- Blocks the commit/PR if version wasn't updated
- Provides helpful error message with suggested version bump

### Release Tag Check
**File:** `.github/workflows/enforce-version-tags.yml`

**Triggers:**
- Push of any tag starting with `v*`

**Behavior:**
- Extracts version from tag (removes `v` prefix)
- Compares tag version with manifest version
- Blocks tag creation if versions don't match
- Checks for changelog entry
- Provides detailed fix instructions

**Example Error:**
```
❌ ERROR: Tag version does not match manifest version!
Tag version: 1.3.6
Manifest version: 1.3.5

To fix this:
1. Update custom_components/homgar/manifest.json to version 1.3.6
2. Commit and push the version bump
3. Recreate the tag
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

## Safe Tag Creation Script

**File:** `scripts/create-release-tag.sh`

**Usage:**
```bash
# Use manifest version (recommended)
./scripts/create-release-tag.sh

# Use specific version (must match manifest)
./scripts/create-release-tag.sh 1.3.6
```

**Features:**
- Ensures tag version matches manifest version
- Checks working directory is clean
- Prevents duplicate tags
- Verifies changelog entry exists
- Creates and pushes tag safely
- Provides next steps for GitHub release

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
5. Create release tag using safe script

### Version Format
- Semantic versioning: `MAJOR.MINOR.PATCH`
- Always increment by 1 for the appropriate level
- No leading zeros (use `1.3.6`, not `1.3.06`)

## Release Workflow

### Safe Release Process
1. **Make changes** and commit with version bump
2. **Test thoroughly** in development environment
3. **Create release tag** using safe script:
   ```bash
   ./scripts/create-release-tag.sh
   ```
4. **Create GitHub release** at the provided URL
5. **Tag enforcement** will verify version match automatically

### Manual Tag Creation (Not Recommended)
```bash
# This will be blocked by GitHub Actions if version doesn't match
git tag v1.3.6
git push origin v1.3.6
```

### Troubleshooting Tag Issues
If tag enforcement fails:
```bash
# Delete wrong tag
git tag -d v1.3.6
git push origin :refs/tags/v1.3.6

# Fix manifest version
# Edit custom_components/homgar/manifest.json

# Create correct tag
./scripts/create-release-tag.sh
```

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

### Tag Creation Failed
Use the safe script instead of manual tagging:
```bash
./scripts/create-release-tag.sh
```

### GitHub Actions Failed
The GitHub Actions checks are safety nets - if they fail:
1. Update the version locally
2. Push the version bump
3. The next push/tag will succeed

## Benefits

1. **Consistent Releases**: Never forget to bump version for releases
2. **Tag Safety**: Release tags always match manifest version
3. **Clear History**: Each version change corresponds to actual code changes
4. **Automated Safety**: Both local and remote protection against version mistakes
5. **Developer Experience**: Immediate feedback during development
6. **Release Automation**: Safe script handles all tag creation steps
