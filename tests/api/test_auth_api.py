"""Tests for auth API email OTP and WeChat endpoints."""

from app.models import UserIdentity
from app.services import auth_service


def test_send_otp_returns_generic_success(client, monkeypatch):
    """Return a generic success payload without exposing the OTP code."""

    def fake_send_email_otp(recipient: str, code: str) -> None:
        """Avoid external SMTP calls during API tests."""
        return None

    monkeypatch.setattr(auth_service, "send_email_otp", fake_send_email_otp)

    response = client.post(
        "/v1/auth/email/send-otp",
        json={"email": "parent@example.com"},
    )

    assert response.status_code == 200
    assert response.json() == {"detail": "Verification code sent"}


def test_verify_email_endpoint_marks_identity_verified(client, db_session):
    """Verify a stored OTP through the public API endpoint."""
    user, _ = auth_service.get_or_create_user_by_identity(db_session, "email", "parent@example.com")
    auth_service.create_email_verification_otp(db_session, "parent@example.com", "123456")
    db_session.commit()

    response = client.post(
        "/v1/auth/email/verify",
        json={"email": "parent@example.com", "code": "123456"},
    )

    db_session.refresh(user)
    identity = next(item for item in user.identities if item.type == "email")
    assert response.status_code == 200
    assert response.json() == {"detail": "Email verified successfully"}
    assert identity.verified_at is not None


def test_verify_email_endpoint_rejects_invalid_code(client):
    """Reject an invalid verification code with a 400 response."""
    response = client.post(
        "/v1/auth/email/verify",
        json={"email": "parent@example.com", "code": "000000"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired OTP code"


def test_wechat_login_returns_503_when_config_missing(client, monkeypatch):
    """Return 503 when WeChat app credentials are not configured."""

    def fake_exchange(code: str) -> dict:
        """Raise a configuration error for the login exchange."""
        raise auth_service.WechatConfigError("WeChat Mini Program login is not configured")

    monkeypatch.setattr(auth_service, "exchange_wechat_code_for_session", fake_exchange)

    response = client.post("/v1/auth/wechat/login", json={"code": "wx-code"})

    assert response.status_code == 503
    assert response.json()["detail"] == "WeChat Mini Program login is not configured"


def test_wechat_login_returns_400_for_wechat_error_code(client, monkeypatch):
    """Return 400 when WeChat responds with an errcode payload."""

    def fake_exchange(code: str) -> dict:
        """Raise a WeChat API error for the login exchange."""
        raise auth_service.WechatAPIError(40029, "invalid code")

    monkeypatch.setattr(auth_service, "exchange_wechat_code_for_session", fake_exchange)

    response = client.post("/v1/auth/wechat/login", json={"code": "wx-code"})

    assert response.status_code == 400
    assert response.json()["detail"] == {"errcode": 40029, "errmsg": "invalid code"}


def test_wechat_login_returns_502_for_upstream_failure(client, monkeypatch):
    """Return 502 when the upstream WeChat HTTP request fails."""

    def fake_exchange(code: str) -> dict:
        """Raise an upstream error for the login exchange."""
        raise auth_service.WechatUpstreamError("Failed to exchange WeChat login code")

    monkeypatch.setattr(auth_service, "exchange_wechat_code_for_session", fake_exchange)

    response = client.post("/v1/auth/wechat/login", json={"code": "wx-code"})

    assert response.status_code == 502
    assert response.json()["detail"] == "Failed to exchange WeChat login code"


def test_wechat_login_binds_unionid_first_and_openid_second(client, db_session, monkeypatch):
    """Create a WeChat user with unionid as primary and openid as a supplemental binding."""

    def fake_exchange(code: str) -> dict:
        """Return a WeChat session payload with both IDs."""
        return {"openid": "openid-1", "unionid": "unionid-1", "session_key": "session-key"}

    monkeypatch.setattr(auth_service, "exchange_wechat_code_for_session", fake_exchange)

    response = client.post(
        "/v1/auth/wechat/login",
        json={"code": "wx-code", "nickname": "Alice", "avatar_url": "https://example.com/avatar.png"},
    )

    identities = db_session.query(UserIdentity).filter(UserIdentity.type == "wechat").all()
    primary_identity = next(item for item in identities if item.identifier == "unionid-1")

    assert response.status_code == 200
    assert response.json()["is_new"] is True
    assert sorted(identity.identifier for identity in identities) == ["openid-1", "unionid-1"]
    assert primary_identity.extra["nickname"] == "Alice"
    assert primary_identity.extra["avatar_url"] == "https://example.com/avatar.png"
