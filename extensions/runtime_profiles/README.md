# Runtime Profiles

Runtime profiles select concrete provider adapters without putting provider imports,
credentials, or vendor configuration into reusable Content Studio Core.

Profiles are JSON instances of `RuntimeProfile`.

## Included profiles

- `profiles/offline.json`
- `profiles/mpt-guarded.json`
- `profiles/openai-reference-guarded.json`
- `verticals/kids_puppies/runtime/profile-guarded.json`

All committed profiles are default-deny.

## Inspect capabilities

```bash
uv run python -m extensions.operator_console.cli runtime-matrix \
  --profile extensions/runtime_profiles/profiles/mpt-guarded.json
```

## Execute the current provider-backed stage

```bash
uv run python -m extensions.operator_console.cli run-runtime \
  --workflow-id <workflow-id> \
  --profile <profile.json>
```

If the profile enables external calls, add `--confirm-external`.

If it also enables paid calls, add `--confirm-paid`.

## Secrets

Do not place credential values in profile options.

Use SecretReference objects, for example:

```json
{
  "schema_version": "1.0.0",
  "scheme": "env",
  "key": "OPENAI_API_KEY"
}
```

The current environment checker only reports availability and never returns the
secret value.

## Provider loading

Concrete provider modules are lazy-loaded only from registered factory methods.
Profile parsing and capability inspection do not import or invoke provider SDKs.
