#!/bin/bash

# Safe tag creation script - ensures tag matches manifest version
# Usage: ./scripts/create-release-tag.sh [version]

set -e

# Get manifest version
MANIFEST_VERSION=$(jq -r '.version' custom_components/homgar/manifest.json)

# Use provided version or manifest version
VERSION=${1:-$MANIFEST_VERSION}

echo "🏷️  Creating release tag for version $VERSION"
echo "Manifest version: $MANIFEST_VERSION"

# Check if versions match
if [ "$VERSION" != "$MANIFEST_VERSION" ]; then
    echo "❌ ERROR: Provided version ($VERSION) doesn't match manifest version ($MANIFEST_VERSION)"
    echo ""
    echo "Options:"
    echo "1. Update manifest.json to version $VERSION and commit"
    echo "2. Use manifest version: ./scripts/create-release-tag.sh $MANIFEST_VERSION"
    echo "3. Force tag creation (not recommended): git tag -f v$VERSION"
    exit 1
fi

# Check if working directory is clean
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ ERROR: Working directory is not clean"
    echo "Please commit or stash changes before creating a release tag"
    git status --porcelain
    exit 1
fi

# Check if tag already exists
if git rev-parse "v$VERSION" >/dev/null 2>&1; then
    echo "❌ ERROR: Tag v$VERSION already exists"
    echo "To delete and recreate:"
    echo "git tag -d v$VERSION"
    echo "git push origin :refs/tags/v$VERSION"
    exit 1
fi

# Check if changelog entry exists
CHANGELOG_ENTRY="## [$VERSION]"
if grep -q "$CHANGELOG_ENTRY" CHANGELOG.md; then
    echo "✅ Changelog entry found for v$VERSION"
else
    echo "⚠️ WARNING: No changelog entry found for v$VERSION"
    echo "Consider adding an entry to CHANGELOG.md"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create the tag
echo "🏷️  Creating tag v$VERSION..."
git tag "v$VERSION"

# Push the tag
echo "📤 Pushing tag to origin..."
git push origin "v$VERSION"

echo "✅ Tag v$VERSION created and pushed successfully!"
echo ""
echo "Next steps:"
echo "1. Create GitHub release: https://github.com/brettmeyerowitz/homeassistant-homgar/releases/new"
echo "2. Tag: v$VERSION"
echo "3. Target: main"
echo "4. Add release notes from CHANGELOG.md"
