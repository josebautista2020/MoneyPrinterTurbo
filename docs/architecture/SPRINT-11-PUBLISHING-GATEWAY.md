# Sprint 11 — Governed Publishing Gateway

## Objective

Add an explicit, auditable publication boundary after Human Review without
reintroducing automatic publication.

Approval remains necessary but is not sufficient. A separate PublishRequest must
pass a default-deny PublishingPolicy before a provider adapter may be invoked.

## Core contracts

### PublishGrant

An allowlisted platform/account pair.

### PublishTarget

A concrete destination containing:

- platform
- account reference
- privacy level
- optional YouTube privacy status
- explicit YouTube made-for-kids declaration

YouTube targets must explicitly declare `youtube_made_for_kids` when policy
requires it.

### PublishingPolicy

Default-deny controls:

- explicit target allowlist
- `live_publish_enabled=False` by default
- maximum targets per request
- maximum live publications per hour
- current approval must be the latest review decision
- explicit YouTube audience declaration
- synthetic-media declaration

Current default live rate is one publication per hour.

### PublishRequest

An explicit publication intent linked to:

- ReviewPackage ID
- approved ReviewDecision ID
- exact approved render URI
- stable idempotency key
- destination targets
- title/description/tags
- synthetic-media declaration
- `dry_run=True` by default

Changing request content changes its SHA-256 request fingerprint.

### PublishResult

Canonical provider-neutral result with one outcome per platform/account target.

### PublicationRecord / PublicationAuditTrail

Append-only publication evidence containing:

- request
- request fingerprint
- result
- idempotency key
- timestamp
- review decision provenance

## Authorization chain

```text
ReviewPackage
     +
ReviewAuditTrail
     +
ReviewDecision(action=approve)
     |
     v
Is approval present in audit?
     |
     v
Is it the latest decision?
     |
     v
Does PublishRequest reference
the exact package/decision/render?
     |
     v
PublishingPolicy
 ├─ target allowlist
 ├─ synthetic declaration
 ├─ YouTube audience declaration
 ├─ target-count limit
 ├─ live-enabled gate
 └─ hourly live rate limit
     |
     v
Idempotency Ledger
     |
     +--> existing same fingerprint -> replay result, no provider call
     |
     +--> same key different payload -> BLOCK
     |
     v
dry_run?
 ├─ yes -> validate + audit only
 └─ no  -> Publisher
```

## Stale approvals

If an approval is followed by:

- rejection
- regenerate-shot
- regenerate-episode
- any later review decision

the earlier approval cannot authorize publication when
`require_latest_approval=True`.

A new explicit approval is required.

## Idempotency

`idempotency_key` is unique in the publication ledger.

If the same key is replayed with the exact same request fingerprint:

- no provider call occurs;
- the stored result is returned with `idempotent_replay=True`.

If the same key is used with a changed request:

- execution fails closed.

## Rate limiting

New live publication requests are limited by
`max_live_publications_per_hour`.

Dry runs do not consume the live rate limit.

Idempotent replays do not create new records and therefore do not consume another
slot.

## Local publication ledger

`extensions/publishing_gateway/store.py` provides
`JsonlPublicationLedger`.

The ledger:

- stores one PublicationRecord per JSONL line;
- rejects duplicate record IDs;
- rejects duplicate idempotency keys;
- reloads and validates every record;
- flushes and fsyncs every append.

This adapter is replaceable by a database implementation without changing the Core
PublicationLedger protocol.

## MoneyPrinterTurbo / Upload-Post adapter

`extensions/mpt_adapter/publishing.py` implements
`MPTUploadPostPublisher`.

It reuses:

`app.services.upload_post.upload_post_service.upload_video(...)`

The adapter is independently fail-closed:

```python
MPTUploadPostPublisher(allow_live_publish=False)
```

Live provider calls require `allow_live_publish=True`.

Additional adapter controls:

- Upload-Post must be configured/enabled;
- approved render must exist locally;
- request account must match configured Upload-Post username;
- one shared privacy level per request;
- YouTube audience declaration must be explicit;
- YouTube metadata maps title, description, tags and privacy status.

## Kids-puppies

Vertical examples live under:

`verticals/kids_puppies/publishing/`

The example YouTube target explicitly sets:

```json
"youtube_made_for_kids": true
```

All committed publishing examples remain:

```json
"live_publish_enabled": false
"dry_run": true
```

No repository example enables live publication.

## Synthetic media

The gateway can require `contains_synthetic_media=True`.

The current MoneyPrinterTurbo Upload-Post implementation already sends
`containsSyntheticMedia=true` for YouTube uploads when YouTube metadata is
present.

## CI safety

All provider calls are monkeypatched/faked.

CI verifies the live adapter mapping without:

- connecting to Upload-Post;
- creating a provider upload request;
- publishing to any social platform;
- incurring provider cost.

## Publication is still explicit

Human approval alone does not publish.

The live path requires **both**:

1. PublishingPolicy.live_publish_enabled=True
2. MPTUploadPostPublisher(allow_live_publish=True)

and must still pass every other gateway rule.

## ADR assessment

No new ADR is required. Publishing remains outside Core rendering/review and behind
the existing anti-corruption boundary.
