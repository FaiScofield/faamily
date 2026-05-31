# Auth Membership Scenario Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the database schema path, complete real WeChat login and email verification, remove the obsolete `child` role, and initialize scenario default folders when a family enables a scenario.

**Architecture:** Keep `SQLAlchemy models + Alembic` as the schema source of truth, add focused auth helpers for SMTP and WeChat exchange, migrate legacy membership data in place, and make scenario initialization idempotent at the service layer. Limit behavior changes to the requested flows and preserve existing API shapes where practical.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL, Pydantic Settings, Python `smtplib`, WeChat Mini Program `jscode2session`, pytest

---

## File Map

- Modify: `d:\MyCodes\faamily\app\core\config.py`
  - Add WeChat and SMTP settings.
- Modify: `d:\MyCodes\faamily\.env.example`
  - Add WeChat and SMTP placeholder values.
- Modify: `d:\MyCodes\faamily\app\models\__init__.py`
  - Add `EmailVerificationOtp`; align role constraint and bigint fields.
- Create: `d:\MyCodes\faamily\migrations\versions\0002_auth_membership_scenario_fix.py`
  - Apply drift fixes and create the new OTP table.
- Modify: `d:\MyCodes\faamily\db\schema.sql`
  - Mirror the canonical schema after the migration.
- Modify: `d:\MyCodes\faamily\app\services\auth_service.py`
  - Add OTP generation/verification, SMTP sending, WeChat exchange helpers.
- Modify: `d:\MyCodes\faamily\app\api\auth.py`
  - Replace placeholder email verification and WeChat login behavior.
- Modify: `d:\MyCodes\faamily\app\services\family_service.py`
  - Remove `child` role handling from validation and comments.
- Modify: `d:\MyCodes\faamily\app\api\families.py`
  - Remove `child` references from request validation and docs.
- Modify: `d:\MyCodes\faamily\app\services\scenario_service.py`
  - Create default folders during scenario enablement.
- Modify: `d:\MyCodes\faamily\README.md`
  - Document SMTP and WeChat configuration.
- Modify: `d:\MyCodes\faamily\next-tasks.md`
  - Remove `child` references from the task list language.
- Create: `d:\MyCodes\faamily\tests\conftest.py`
  - Shared pytest fixtures for DB session and app client.
- Create: `d:\MyCodes\faamily\tests\services\test_auth_service.py`
  - OTP and WeChat service tests.
- Create: `d:\MyCodes\faamily\tests\services\test_scenario_service.py`
  - Scenario initialization tests.
- Create: `d:\MyCodes\faamily\tests\api\test_auth_api.py`
  - Email verify and WeChat API tests.
- Create: `d:\MyCodes\faamily\tests\migrations\test_membership_migration.py`
  - Regression check for `child -> member + restricted`.

### Task 1: Add Config Surface For WeChat And SMTP

**Files:**
- Modify: `d:\MyCodes\faamily\app\core\config.py`
- Modify: `d:\MyCodes\faamily\.env.example`
- Test: `d:\MyCodes\faamily\tests\services\test_auth_service.py`

- [ ] **Step 1: Write the failing config test**

```python
from app.core.config import Settings


def test_settings_load_wechat_and_smtp_values():
    settings = Settings.model_validate(
        {
            "database_url": "sqlite:///./data.db",
            "jwt_secret": "secret",
            "wechat_app_id": "wx-app-id",
            "wechat_app_secret": "wx-secret",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "bot@example.com",
            "smtp_password": "pwd",
            "smtp_from_email": "bot@example.com",
        }
    )

    assert settings.wechat_app_id == "wx-app-id"
    assert settings.smtp_host == "smtp.example.com"
    assert settings.smtp_port == 587
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_auth_service.py::test_settings_load_wechat_and_smtp_values -v`
Expected: FAIL with missing fields or unknown attributes on `Settings`.

- [ ] **Step 3: Write minimal config implementation**

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str
    jwt_secret: str
    jwt_access_token_expires_minutes: int = 30
    jwt_refresh_token_expires_days: int = 30

    admin_user_ids: str = ""
    online_timeout_minutes: int = 15

    wechat_app_id: str | None = None
    wechat_app_secret: str | None = None
    wechat_api_base: str = "https://api.weixin.qq.com"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
```

- [ ] **Step 4: Update `.env.example`**

```env
WECHAT_APP_ID=
WECHAT_APP_SECRET=
WECHAT_API_BASE=https://api.weixin.qq.com
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/services/test_auth_service.py::test_settings_load_wechat_and_smtp_values -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py .env.example tests/services/test_auth_service.py
git commit -m "feat: add wechat and smtp configuration"
```

### Task 2: Align Models And Add Migration For Drift Fixes

**Files:**
- Modify: `d:\MyCodes\faamily\app\models\__init__.py`
- Create: `d:\MyCodes\faamily\migrations\versions\0002_auth_membership_scenario_fix.py`
- Modify: `d:\MyCodes\faamily\db\schema.sql`
- Test: `d:\MyCodes\faamily\tests\migrations\test_membership_migration.py`

- [ ] **Step 1: Write the failing migration behavior test**

```python
def test_child_membership_is_converted_to_restricted_member(db_session):
    db_session.execute(
        """
        insert into memberships (id, family_id, user_id, role, permissions, status, joined_at, created_at, updated_at)
        values (
            gen_random_uuid(),
            :family_id,
            :user_id,
            'child',
            '{}'::jsonb,
            'active',
            now(),
            now(),
            now()
        )
        """,
        {"family_id": FAMILY_ID, "user_id": USER_ID},
    )
    db_session.commit()

    run_upgrade("0002_auth_membership_scenario_fix")

    row = db_session.execute("select role, permissions from memberships where user_id = :user_id", {"user_id": USER_ID}).one()
    assert row.role == "member"
    assert row.permissions["restricted"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/migrations/test_membership_migration.py::test_child_membership_is_converted_to_restricted_member -v`
Expected: FAIL because the migration does not exist yet.

- [ ] **Step 3: Update ORM models**

```python
class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'owner' | 'admin' | 'member'",
    )
    permissions: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
        comment="Flag-based permissions, e.g. {'restricted': true}",
    )
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'admin', 'member')", name="chk_memberships_role"),
        ...
    )


class EmailVerificationOtp(Base):
    __tablename__ = "email_verification_otps"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        Index("idx_email_verification_otps_email_expires", "email", "expires_at"),
    )
```

- [ ] **Step 4: Write the migration**

```python
def upgrade() -> None:
    op.create_table(
        "email_verification_otps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_email_verification_otps_email_expires",
        "email_verification_otps",
        ["email", "expires_at"],
    )

    op.execute(
        """
        update memberships
        set role = 'member',
            permissions = coalesce(permissions, '{}'::jsonb) || '{"restricted": true}'::jsonb
        where role = 'child'
        """
    )
    op.drop_constraint("chk_memberships_role", "memberships", type_="check")
    op.create_check_constraint(
        "chk_memberships_role",
        "memberships",
        "role IN ('owner', 'admin', 'member')",
    )
    op.alter_column("files", "size_bytes", type_=sa.BigInteger(), existing_type=sa.Integer())
    op.alter_column("quotas", "total_bytes", type_=sa.BigInteger(), existing_type=sa.Integer())
    op.alter_column("quotas", "used_bytes", type_=sa.BigInteger(), existing_type=sa.Integer())
```

- [ ] **Step 5: Mirror the canonical schema into `db/schema.sql`**

```sql
constraint chk_memberships_role check (role in ('owner', 'admin', 'member')),

create table if not exists email_verification_otps (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  code_hash text not null,
  expires_at timestamptz not null,
  consumed_at timestamptz null,
  created_at timestamptz not null default now()
);

create index if not exists idx_email_verification_otps_email_expires
  on email_verification_otps(email, expires_at desc);
```

- [ ] **Step 6: Run migration test and Alembic smoke check**

Run: `pytest tests/migrations/test_membership_migration.py::test_child_membership_is_converted_to_restricted_member -v`
Expected: PASS

Run: `alembic upgrade head`
Expected: migration applies without errors

- [ ] **Step 7: Commit**

```bash
git add app/models/__init__.py migrations/versions/0002_auth_membership_scenario_fix.py db/schema.sql tests/migrations/test_membership_migration.py
git commit -m "feat: align schema and migrate membership role"
```

### Task 3: Implement Account Email OTP Sending And Verification

**Files:**
- Modify: `d:\MyCodes\faamily\app\services\auth_service.py`
- Modify: `d:\MyCodes\faamily\app\api\auth.py`
- Test: `d:\MyCodes\faamily\tests\services\test_auth_service.py`
- Test: `d:\MyCodes\faamily\tests\api\test_auth_api.py`

- [ ] **Step 1: Write the failing service test**

```python
def test_verify_email_otp_marks_identity_verified(db_session, email_identity):
    otp = create_email_verification_otp(db_session, "parent@example.com", "123456")
    verify_email_otp(db_session, "parent@example.com", "123456")

    db_session.refresh(email_identity)
    assert email_identity.verified_at is not None
    assert otp.consumed_at is not None
```

- [ ] **Step 2: Write the failing API test**

```python
def test_send_otp_returns_generic_success(client, monkeypatch):
    monkeypatch.setattr("app.services.auth_service.send_email_otp", lambda *args, **kwargs: None)
    response = client.post("/v1/auth/email/send-otp", json={"email": "parent@example.com"})
    assert response.status_code == 200
    assert response.json() == {"detail": "Verification code sent"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/services/test_auth_service.py::test_verify_email_otp_marks_identity_verified -v`
Expected: FAIL because helper functions do not exist.

Run: `pytest tests/api/test_auth_api.py::test_send_otp_returns_generic_success -v`
Expected: FAIL because the endpoint still returns placeholder behavior.

- [ ] **Step 4: Implement auth service helpers**

```python
def generate_otp_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def hash_otp_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def create_email_verification_otp(db: Session, email: str, code: str, ttl_minutes: int = 10) -> EmailVerificationOtp:
    otp = EmailVerificationOtp(
        email=email,
        code_hash=hash_otp_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    )
    db.add(otp)
    db.flush()
    return otp


def verify_email_otp(db: Session, email: str, code: str) -> EmailVerificationOtp:
    otp = (
        db.query(EmailVerificationOtp)
        .filter(
            EmailVerificationOtp.email == email,
            EmailVerificationOtp.code_hash == hash_otp_code(code),
            EmailVerificationOtp.consumed_at.is_(None),
            EmailVerificationOtp.expires_at > datetime.now(timezone.utc),
        )
        .order_by(EmailVerificationOtp.created_at.desc())
        .first()
    )
    if not otp:
        raise ValueError("Invalid or expired OTP code")

    otp.consumed_at = datetime.now(timezone.utc)
    identity = db.query(UserIdentity).filter(UserIdentity.type == "email", UserIdentity.identifier == email).first()
    if identity and identity.verified_at is None:
        identity.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(otp)
    return otp
```

- [ ] **Step 5: Implement SMTP sending**

```python
def send_email_otp(recipient: str, code: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise RuntimeError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = "Faamily verification code"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(f"Your Faamily verification code is: {code}")

    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as client:
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password or "")
            client.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as client:
            if settings.smtp_use_tls:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password or "")
            client.send_message(message)
```

- [ ] **Step 6: Replace placeholder API logic**

```python
@router.post("/email/send-otp")
@limiter.limit("3/minute")
def email_send_otp(request: Request, body: EmailSendOtpRequest, db: Session = Depends(get_db)):
    code = generate_otp_code()
    try:
        create_email_verification_otp(db, body.email, code)
        send_email_otp(body.email, code)
        db.commit()
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to send verification email")
    return {"detail": "Verification code sent"}


@router.post("/email/verify")
def email_verify(body: EmailVerifyRequest, db: Session = Depends(get_db)):
    try:
        verify_email_otp(db, body.email, body.code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"detail": "Email verified successfully"}
```

- [ ] **Step 7: Run targeted tests**

Run: `pytest tests/services/test_auth_service.py::test_verify_email_otp_marks_identity_verified -v`
Expected: PASS

Run: `pytest tests/api/test_auth_api.py::test_send_otp_returns_generic_success -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/services/auth_service.py app/api/auth.py tests/services/test_auth_service.py tests/api/test_auth_api.py
git commit -m "feat: add real account email verification flow"
```

### Task 4: Implement Real WeChat Mini Program Login

**Files:**
- Modify: `d:\MyCodes\faamily\app\services\auth_service.py`
- Modify: `d:\MyCodes\faamily\app\api\auth.py`
- Test: `d:\MyCodes\faamily\tests\services\test_auth_service.py`
- Test: `d:\MyCodes\faamily\tests\api\test_auth_api.py`

- [ ] **Step 1: Write the failing WeChat exchange test**

```python
def test_exchange_wechat_code_returns_openid_and_unionid(monkeypatch):
    class DummyResponse:
        status_code = 200

        def json(self):
            return {"openid": "openid-1", "unionid": "unionid-1", "session_key": "abc"}

        def raise_for_status(self):
            return None

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: DummyResponse())

    result = exchange_wechat_code("wx-code")
    assert result["openid"] == "openid-1"
    assert result["unionid"] == "unionid-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_auth_service.py::test_exchange_wechat_code_returns_openid_and_unionid -v`
Expected: FAIL because the exchange helper does not exist.

- [ ] **Step 3: Add the HTTP dependency**

```text
httpx==0.27.2
```

- [ ] **Step 4: Implement the exchange helper**

```python
def exchange_wechat_code(code: str) -> dict:
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise RuntimeError("WeChat Mini Program login is not configured")

    response = httpx.get(
        f"{settings.wechat_api_base}/sns/jscode2session",
        params={
            "appid": settings.wechat_app_id,
            "secret": settings.wechat_app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("errcode"):
        raise ValueError(data.get("errmsg") or "WeChat code exchange failed")
    if not data.get("openid"):
        raise RuntimeError("WeChat response missing openid")
    return data
```

- [ ] **Step 5: Replace the placeholder endpoint behavior**

```python
@router.post("/wechat/login", response_model=WechatLoginResponse)
@limiter.limit("10/minute")
def wechat_login(request: Request, body: WechatLoginRequest, db: Session = Depends(get_db)):
    try:
        wechat_data = exchange_wechat_code(body.code)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="WeChat login service unavailable")

    openid = wechat_data["openid"]
    unionid = wechat_data.get("unionid")
    identifier = unionid or openid

    user, is_new = get_or_create_user_by_identity(
        db,
        "wechat",
        identifier,
        provider="wechat_miniprogram",
    )

    if unionid and unionid != openid:
        bind_identity_to_user(db, user, "wechat", openid, provider="wechat_miniprogram_openid", verified=True)

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    return WechatLoginResponse(
        user_id=str(user.id),
        access_token=access_token,
        refresh_token=refresh_token,
        is_new=is_new,
    )
```

- [ ] **Step 6: Run targeted tests**

Run: `pytest tests/services/test_auth_service.py::test_exchange_wechat_code_returns_openid_and_unionid -v`
Expected: PASS

Run: `pytest tests/api/test_auth_api.py -k wechat -v`
Expected: PASS for success and error cases

- [ ] **Step 7: Commit**

```bash
git add requirements.txt app/services/auth_service.py app/api/auth.py tests/services/test_auth_service.py tests/api/test_auth_api.py
git commit -m "feat: add real wechat mini program login"
```

### Task 5: Remove `child` Role References From Family Flows

**Files:**
- Modify: `d:\MyCodes\faamily\app\services\family_service.py`
- Modify: `d:\MyCodes\faamily\app\api\families.py`
- Modify: `d:\MyCodes\faamily\next-tasks.md`
- Test: `d:\MyCodes\faamily\tests\api\test_auth_api.py`

- [ ] **Step 1: Write the failing validation test**

```python
def test_update_member_role_rejects_child(client, owner_token, membership_id):
    response = client.patch(
        f"/v1/families/{FAMILY_ID}/members/{membership_id}/role",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"role": "child"},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_auth_api.py::test_update_member_role_rejects_child -v`
Expected: FAIL if the API still accepts `child`.

- [ ] **Step 3: Update service and API validation**

```python
ALLOWED_MEMBERSHIP_ROLES = {"owner", "admin", "member"}


if new_role not in ALLOWED_MEMBERSHIP_ROLES:
    raise ValueError("Role must be one of: owner, admin, member")
```

```python
class UpdateMemberRoleRequest(BaseModel):
    role: Literal["owner", "admin", "member"]
```

- [ ] **Step 4: Update docs and comments**

```markdown
- [x] 成员管理：列成员、改角色（owner/admin/member）、移除成员
```

- [ ] **Step 5: Run the validation test**

Run: `pytest tests/api/test_auth_api.py::test_update_member_role_rejects_child -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/family_service.py app/api/families.py next-tasks.md tests/api/test_auth_api.py
git commit -m "refactor: remove child membership role"
```

### Task 6: Initialize Scenario Default Folders Idempotently

**Files:**
- Modify: `d:\MyCodes\faamily\app\services\scenario_service.py`
- Test: `d:\MyCodes\faamily\tests\services\test_scenario_service.py`

- [ ] **Step 1: Write the failing scenario test**

```python
def test_enable_scenario_creates_default_folders_once(db_session, seeded_template, family):
    first = enable_scenario(db_session, str(family.id), str(seeded_template.id))
    second = disable_then_enable_same_scenario(db_session, first)

    folders = db_session.query(Folder).filter(Folder.family_id == family.id).all()
    names = sorted((folder.zone, folder.name) for folder in folders)
    assert names.count(("shared", "学习资料")) == 1
    assert names.count(("vault", "成绩单")) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_scenario_service.py::test_enable_scenario_creates_default_folders_once -v`
Expected: FAIL because folders are not created yet.

- [ ] **Step 3: Add the initialization helper**

```python
def ensure_scenario_default_folders(db: Session, family_id: str, template_definition: dict) -> None:
    default_folders = template_definition.get("default_folders", [])
    for item in default_folders:
        zone = item.get("zone")
        name = item.get("name")
        if not zone or not name:
            continue

        existing = (
            db.query(Folder)
            .filter(
                Folder.family_id == family_id,
                Folder.zone == zone,
                Folder.parent_id.is_(None),
                Folder.name == name,
            )
            .first()
        )
        if existing:
            continue

        db.add(Folder(family_id=family_id, zone=zone, name=name, parent_id=None))
```

- [ ] **Step 4: Call the helper from `enable_scenario()`**

```python
template = get_template(db, template_id)
if not template:
    raise ValueError("Scenario template not found")

instance = ScenarioInstance(
    family_id=family_id,
    template_id=template_id,
    status="enabled",
    config=config or {},
)
db.add(instance)
db.flush()
ensure_scenario_default_folders(db, family_id, template.definition or {})
db.commit()
db.refresh(instance)
return instance
```

- [ ] **Step 5: Run the scenario test**

Run: `pytest tests/services/test_scenario_service.py::test_enable_scenario_creates_default_folders_once -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/scenario_service.py tests/services/test_scenario_service.py
git commit -m "feat: initialize scenario default folders"
```

### Task 7: Update Docs And Run Final Focused Checks

**Files:**
- Modify: `d:\MyCodes\faamily\README.md`
- Test: `d:\MyCodes\faamily\tests\api\test_auth_api.py`
- Test: `d:\MyCodes\faamily\tests\services\test_auth_service.py`
- Test: `d:\MyCodes\faamily\tests\services\test_scenario_service.py`
- Test: `d:\MyCodes\faamily\tests\migrations\test_membership_migration.py`

- [ ] **Step 1: Update README configuration examples**

```markdown
## Auth Configuration

- `WECHAT_APP_ID` / `WECHAT_APP_SECRET`: required for real mini program login
- `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL`: required for account email verification
```

- [ ] **Step 2: Run focused regression tests**

Run: `pytest tests/services/test_auth_service.py tests/services/test_scenario_service.py tests/api/test_auth_api.py tests/migrations/test_membership_migration.py -v`
Expected: PASS

- [ ] **Step 3: Run migration and diagnostics checks**

Run: `alembic upgrade head`
Expected: PASS

Run: `python -m compileall app`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document auth and scenario setup"
```

## Self-Review Checklist

- Spec coverage:
  - schema drift: Tasks 1, 2, 7
  - email verification: Tasks 1, 3, 7
  - WeChat login: Tasks 1, 4, 7
  - remove `child`: Tasks 2, 5
  - scenario folder initialization: Task 6
- Placeholder scan:
  - no `TODO`, `TBD`, or “implement later” steps remain
- Type consistency:
  - membership roles are consistently `owner/admin/member`
  - OTP storage for account verification consistently uses `email_verification_otps`
  - folder initialization uses top-level folders only in this plan
