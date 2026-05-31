# 2026-05-31 Auth Membership Scenario Design

## Summary

This design documents four backend corrections for the Faamily project:

1. align database schema sources across ORM, Alembic, and `db/schema.sql`
2. complete real WeChat Mini Program login
3. complete email verification for account identity
4. remove the `child` membership role and use permission flags instead
5. initialize default scenario structure when enabling a scenario

The implementation goal is to close the requested gaps with the smallest possible behavior-preserving changes, while making `SQLAlchemy models + Alembic migrations` the authoritative schema path.

## Scope

In scope:

- schema consistency fixes for the affected tables and constraints
- a new Alembic migration that upgrades existing databases safely
- WeChat `code -> openid/unionid` exchange through the official API
- email OTP sending and verification for account identities
- migration of legacy `child` memberships to `member + permissions.restricted=true`
- idempotent scenario folder initialization from template definitions

Out of scope:

- object storage signed upload/download redesign
- a new generalized policy engine for fine-grained permissions
- automatic task/contact/reminder creation from scenario templates
- CI, deployment, or test infrastructure beyond focused checks for this change

## Current Problems

### Schema Drift

The project currently has three schema sources that are not fully aligned:

- ORM models in `app/models/__init__.py`
- Alembic base migration in `migrations/versions/0001_init.py`
- SQL bootstrap file in `db/schema.sql`

Known differences include:

- `memberships.role` still allows `child` in `db/schema.sql` but not in ORM and Alembic
- `files.size_bytes`, `quotas.total_bytes`, and `quotas.used_bytes` use different numeric types between SQL bootstrap and Alembic
- folder uniqueness semantics differ between bootstrap SQL and Alembic
- email verification currently reuses `vault_email_otps`, which mixes account verification with vault secondary verification

### Incomplete M1

- `/auth/wechat/login` still treats the incoming code as an identity placeholder instead of exchanging it via WeChat
- `/auth/email/send-otp` does not actually send email
- account email verification and vault verification share the same OTP table even though they serve different purposes

### Membership Semantics

- code and docs still contain historical references to the deleted `child` role
- actual product direction is `owner/admin/member` plus permission flags

### Scenario Enablement Gap

- enabling a scenario creates a `scenario_instance` but does not initialize the default folders declared in the template definition

## Design Decisions

### Source of Truth

`SQLAlchemy ORM models + Alembic migrations` become the canonical schema source.

Rules:

- all structural changes are introduced through new Alembic migrations
- `db/schema.sql` is maintained only as a bootstrap mirror of the current canonical schema
- existing migration `0001_init.py` is not rewritten in place; a follow-up migration fixes drift for existing databases

This avoids breaking environments that have already applied the first revision.

### Email OTP Separation

Account email verification will use a dedicated table instead of `vault_email_otps`.

New table:

- `email_verification_otps`
  - `id`
  - `email`
  - `code_hash`
  - `expires_at`
  - `consumed_at`
  - `created_at`

Rationale:

- account verification and vault access are different security flows
- account verification does not require `user_id`
- reusing `vault_email_otps` currently conflicts with the non-null `user_id` constraint

### Role Model

Supported membership roles:

- `owner`
- `admin`
- `member`

Child-like limitations move into `memberships.permissions`.

Migration rule for historical data:

- if `role = 'child'`, update to `role = 'member'`
- merge `{"restricted": true}` into `permissions`

This preserves behavior while removing the obsolete role value from the schema and code.

### Scenario Initialization Policy

Scenario enablement will initialize only `definition.default_folders`.

Behavior:

- create folders after enabling a scenario
- creation is idempotent
- re-enabling a disabled scenario re-runs initialization and only fills missing folders
- existing user-created folders are preserved

This keeps the change focused and avoids expanding scope into task or record bootstrap generation.

## Data Model Changes

### New Table

Add `email_verification_otps`.

Recommended columns:

- `id uuid primary key`
- `email text not null`
- `code_hash text not null`
- `expires_at timestamptz not null`
- `consumed_at timestamptz null`
- `created_at timestamptz not null default now()`

Recommended index:

- `(email, expires_at desc)`

### Membership Constraint Updates

Update membership role checks everywhere to:

- `role IN ('owner', 'admin', 'member')`

No schema-level `child` value remains after this change.

### Numeric Type Alignment

Align the following to `BigInteger` / `bigint` consistently:

- `files.size_bytes`
- `quotas.total_bytes`
- `quotas.used_bytes`

This matches storage quota semantics better and avoids size overflow risk.

### Folder Uniqueness Alignment

Preserve the existing intended uniqueness semantics for nested folders:

- unique by `family_id + zone + normalized parent_id + name`

Alembic and bootstrap SQL must express the same rule.

## Component Changes

### Config

Extend `app/core/config.py` with:

- `wechat_app_id`
- `wechat_app_secret`
- `wechat_api_base` defaulting to the official API base
- `smtp_host`
- `smtp_port`
- `smtp_username`
- `smtp_password`
- `smtp_from_email`
- `smtp_use_tls`
- optional `smtp_use_ssl`

These values remain optional at load time, but the related endpoints fail fast with clear errors when required settings are missing.

### Auth Service

Add service helpers for:

- generating and hashing OTP codes
- persisting account email verification OTPs
- sending verification emails through SMTP
- consuming and validating account email OTPs
- exchanging WeChat Mini Program code for session data
- upserting WeChat identities with `unionid` priority and `openid` secondary binding

The WeChat exchange helper returns:

- `openid`
- optional `unionid`
- optional `session_key`

The session key is not persisted for this iteration.

### Auth API

#### `/auth/email/send-otp`

Flow:

1. validate email input
2. generate a six-digit OTP
3. store only the hash in `email_verification_otps`
4. send the code via SMTP email
5. return a generic success message

Behavior:

- do not return the OTP in API responses
- in local development, the server may log that an OTP was sent, but never logs the plaintext code unless explicitly allowed by config in the future

#### `/auth/email/verify`

Flow:

1. find an unconsumed, unexpired OTP for the email by hash
2. mark it consumed
3. mark any matching email identity as verified
4. return success

If the email identity does not exist, OTP verification succeeds only for the OTP record but does not invent a new identity implicitly.

#### `/auth/wechat/login`

Flow:

1. exchange `body.code` via WeChat `jscode2session`
2. validate response and extract `openid` and optional `unionid`
3. use `unionid` as the primary identifier when available, otherwise use `openid`
4. get or create the user by the primary identifier
5. when `unionid` and `openid` are both present and distinct, bind the `openid` identity to the same user
6. update profile metadata such as nickname and avatar for newly created or existing WeChat identities as appropriate
7. issue access and refresh tokens

Error handling:

- invalid or expired code from WeChat: 400
- upstream WeChat failure or malformed response: 502
- missing server configuration: 503

## Membership and Permissions Changes

### API and Service Validation

Update family-related validation and help text so that:

- role input accepts only `owner/admin/member`
- comments and docstrings stop mentioning `child`
- user-facing messages describe restrictions through permissions instead of role names

### Permission Compatibility

Existing permission checks that already use flags like `restricted` remain valid.

No new generalized permission engine is introduced in this change. The goal is only to remove the obsolete role and standardize the current direction.

## Scenario Initialization

### Initialization Trigger

`app/services/scenario_service.py::enable_scenario()` will call a helper after the scenario instance is enabled.

Suggested helper:

- `ensure_scenario_default_folders(db, family_id, template_definition)`

### Folder Creation Rules

For each item in `definition.default_folders`:

- require `zone`
- require `name`
- optional `parent_path` is not introduced in this iteration
- create as a top-level folder if it does not already exist

Idempotency rule:

- query by `family_id`, `zone`, `parent_id is null`, and `name`
- create only when missing

If a scenario is re-enabled, the helper is run again to backfill missing folders without duplicating existing ones.

## Migration Plan

Create a new Alembic revision after `0001_init` that:

1. creates `email_verification_otps`
2. updates old `child` memberships to `member` and injects `restricted=true` into `permissions`
3. drops and recreates the membership role check constraint if needed
4. aligns folder uniqueness expression if needed
5. alters quota and file byte columns to `bigint` where needed

Then update:

- ORM models
- `db/schema.sql`
- related schema docs and comments

`0001_init.py` should stay untouched unless it has not been used by any shared environment. For safety, this design assumes it remains unchanged and a new revision performs the correction.

## Error Handling

### WeChat Login

- missing `openid`: treat as upstream invalid response
- WeChat error code returned: convert to API error with safe message
- duplicate binding conflict: resolve by loading the existing identity owner when valid, otherwise fail with conflict

### Email Verification

- expired OTP: 400
- consumed OTP: 400
- wrong OTP: 400
- SMTP failure before persistence commit: no OTP row persisted
- SMTP failure after persistence flush but before commit: rollback transaction

### Scenario Initialization

- if folder initialization fails, the scenario enable operation should rollback as one transaction
- partial folder creation must not remain committed on failure

## Testing Strategy

Focused coverage for this change should include:

- WeChat login success with `unionid`
- WeChat login success with only `openid`
- WeChat login invalid code failure
- email OTP send and verify happy path
- email OTP expired and wrong code cases
- migration of `child` memberships to restricted `member`
- scenario enablement creates missing default folders
- scenario re-enable does not duplicate folders

If the repository does not yet contain a full automated test setup, at minimum add targeted tests around the touched service logic and API endpoints.

## Rollout Notes

- `.env.example` must be updated with placeholders for WeChat and SMTP settings
- README should describe the new required configuration for real WeChat login and SMTP-based email verification
- any developer-only OTP response payload must be removed from account verification endpoints

## Success Criteria

This work is complete when:

- the database schema is consistent across ORM, Alembic, and bootstrap SQL for the affected areas
- `/auth/wechat/login` uses the real WeChat exchange flow
- `/auth/email/send-otp` sends a real verification email and `/auth/email/verify` verifies it
- no active code path, migration constraint, or document relies on a `child` role
- enabling a scenario creates its default folders exactly once and remains idempotent
