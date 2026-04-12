# Adding Device Support

## Default Path

Most new device support should start with:

```text
custom_components/homgar/data/product_models.json
```

The project is intentionally data-driven. Do not start with a custom decoder unless the payload format truly requires it.

## Expected Workflow

1. Identify the reported model
2. Capture one or more real raw payloads
3. Confirm whether the model already exists in `product_models.json`
4. Verify the decoded fields through `decode_payload(model, payload)`
5. Add regression coverage using the payload corpus
6. Update public docs if support or entities changed

## When `decoder.py` Should Change

Change `decoder.py` only when:
- a payload format is not covered by the current generic decoder path
- a field extraction rule is wrong for an existing format
- a model family needs shared special handling that cannot be expressed in `product_models.json`

Avoid per-model one-off code unless there is no practical generic path.

## Required Documentation Updates

If device support changes user-visible behavior, update:
- `README.md` supported model list
- `README.md` entities table when new decoded fields are exposed
- `CHANGELOG.md`
- `docs/test-corpus.md` when new payload samples are added

## Contributor Expectations

When proposing new model support, include:
- model name
- raw payloads
- expected readings from the app if available
- source issue number
- regression fixture updates
