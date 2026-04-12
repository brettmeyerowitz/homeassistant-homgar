# Releasing

## Release Checklist

1. Bump `custom_components/homgar/manifest.json`
2. Add the new section to `CHANGELOG.md`
3. Run:

```bash
bash scripts/pre-commit-docker-test.sh
```

4. Commit the release changes
5. Push `main`
6. Create and push tag `vX.Y.Z`
7. Create the GitHub release with `gh` using a notes file

## Notes File Rule

When using `gh`, write multi-line release notes to a file first and pass:
- `--notes-file`
- `--body-file`

Do not inline large multi-line note bodies directly in shell commands.

## Tagging

The repository includes:

```bash
bash scripts/create-release-tag.sh
```

That script expects a clean working tree and a matching changelog entry.

## Practical Note

If unrelated local ignored/untracked files prevent the helper script from running, the equivalent safe manual flow is:
- ensure `main` is pushed
- create and push the matching tag
- generate release notes from `CHANGELOG.md`
- run `gh release create`
