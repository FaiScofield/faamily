# Email OTP Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SMTP and WeChat config surface, introduce dedicated account email OTP storage, align schema artifacts, and implement the real `/auth/email/send-otp` and `/auth/email/verify` flow with focused tests.

**Architecture:** Keep `SQLAlchemy models + Alembic migrations` as the schema source of truth, mirror the same shape in `db/schema.sql`, and isolate account email verification from vault OTP storage by adding a dedicated `EmailVerificationOtp` model and table. Implement the email OTP flow in the auth service and auth API only, and leave WeChat login and scenario initialization untouched.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, Pydantic Settings, Python `smtplib`, pytest

---

## File Map

- Modify: `d:\MyCodes\faamily\app\core\config.py`
  - Add SMTP and WeChat settings.
- Modify: `d:\MyCodes\faamily\.env.example`
  - Add placeholder environment variables.
- Modify: `d:\MyCodes\faamily\app\models\__init__.py`
  - Add `EmailVerificationOtp` and align bigint types.
- Create: `d:\MyCodes\faamily\migrations\versions\0002_email_otp_schema_fix.py`
  - Add the new OTP table and schema/data corrections.
- Modify: `d:\MyCodes\faamily\db\schema.sql`
  - Mirror the canonical schema.
- Modify: `d:\MyCodes\faamily\app\services\auth_service.py`
  - Add email OTP helpers and SMTP sending.
- Modify: `d:\MyCodes\faamily\app\api\auth.py`
  - Replace placeholder OTP endpoints with the real flow.
- Create: `d:\MyCodes\faamily\tests\conftest.py`
  - Add a minimal shared test setup.
- Create: `d:\MyCodes\faamily\tests\services\test_auth_service.py`
  - Cover config loading and email OTP service behavior.
- Create: `d:\MyCodes\faamily\tests\api\test_auth_api.py`
  - Cover the public OTP endpoints.

## Tasks

### Task 1: Add Failing Tests For Config And Email OTP Flow

**Files:**
- Create: `d:\MyCodes\faamily\tests\conftest.py`
- Create: `d:\MyCodes\faamily\tests\services\test_auth_service.py`
- Create: `d:\MyCodes\faamily\tests\api\test_auth_api.py`

- [ ] Add the minimal pytest fixtures for SQLite sessions and FastAPI `TestClient`.
- [ ] Write a failing config test that expects SMTP and WeChat settings to load from `Settings.model_validate(...)`.
- [ ] Write a failing service test that expects OTP verification to consume the OTP and mark the email identity verified.
- [ ] Write a failing API test that expects `/v1/auth/email/send-otp` to return only a generic success payload.
- [ ] Run the targeted tests and confirm they fail for the expected missing implementation reasons.

### Task 2: Implement Config Surface And Canonical Schema Changes

**Files:**
- Modify: `d:\MyCodes\faamily\app\core\config.py`
- Modify: `d:\MyCodes\faamily\.env.example`
- Modify: `d:\MyCodes\faamily\app\models\__init__.py`
- Create: `d:\MyCodes\faamily\migrations\versions\0002_email_otp_schema_fix.py`
- Modify: `d:\MyCodes\faamily\db\schema.sql`

- [ ] Add SMTP and WeChat settings to `Settings` with safe defaults.
- [ ] Add `EmailVerificationOtp` to the ORM models.
- [ ] Align `files.size_bytes`, `quotas.total_bytes`, and `quotas.used_bytes` to bigint in the canonical model/schema path.
- [ ] Add the Alembic migration that creates `email_verification_otps`, migrates legacy `child` rows to `member + restricted`, and applies bigint alignment.
- [ ] Mirror the same schema shape in `db/schema.sql`.

### Task 3: Implement Real Email OTP Send And Verify Flow

**Files:**
- Modify: `d:\MyCodes\faamily\app\services\auth_service.py`
- Modify: `d:\MyCodes\faamily\app\api\auth.py`

- [ ] Add OTP generation, hashing, persistence, sending, and verification helpers to the auth service.
- [ ] Replace placeholder `/auth/email/send-otp` behavior with the SMTP-backed flow.
- [ ] Replace placeholder `/auth/email/verify` behavior with the real consume-and-verify flow.
- [ ] Preserve the current email registration/login behavior and do not change WeChat login.

### Task 4: Verify With Focused Checks

**Files:**
- Test: `d:\MyCodes\faamily\tests\services\test_auth_service.py`
- Test: `d:\MyCodes\faamily\tests\api\test_auth_api.py`

- [ ] Run the focused service and API tests and make them green.
- [ ] Run an Alembic upgrade smoke check.
- [ ] Run diagnostics on touched Python files and fix any introduced issues.
