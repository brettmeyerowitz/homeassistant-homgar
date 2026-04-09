---
description: Create and publish a GitHub release
---

## Steps to create a release

1. Decide version bump:
   - **patch** (x.x.X): bug fixes, minor improvements, new sub-device decoders
   - **minor** (x.X.0): new hub/device category support, significant new features
   - **major** (X.0.0): breaking changes, full rewrites

2. Update `custom_components/homgar/manifest.json` — bump `"version"`

3. Update `CHANGELOG.md` — add new `## [x.x.x] - YYYY-MM-DD` section above previous release with `### 🐛 BUG FIXES`, `### ✨ NEW FEATURES`, `### 🔧 INTERNAL` sections as appropriate

4. Update `README.md` — bump the version in the `manifest.json` code snippet (search for the old version string)

5. Run pre-commit tests to confirm everything passes:
// turbo
```
bash scripts/pre-commit-docker-test.sh
```

6. Commit all changes:
// turbo
```
git add -A && git commit -m "vX.X.X: <short description>"
```

7. Run the release tag script:
// turbo
```
bash scripts/create-release-tag.sh
```

8. Create the GitHub release using `gh`:
```
gh release create vX.X.X --title "vX.X.X" --notes-file <(sed -n '/## \[X.X.X\]/,/## \[/{ /## \[X.X.X\]/d; /## \[/d; p }' CHANGELOG.md)
```

   Or with a specific version (replace X.X.X):
```
VERSION=2.1.1
gh release create "v$VERSION" \
  --title "v$VERSION" \
  --notes "$(awk "/## \[$VERSION\]/{found=1; next} found && /^## \[/{exit} found{print}" CHANGELOG.md)"
```

9. Comment on any GitHub issues fixed by this release pointing users to upgrade.
