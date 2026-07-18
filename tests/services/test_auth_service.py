"""Tests for auth service email OTP and WeChat login behavior."""

import httpx
import pytest

from app.core.config import Settings
from app.models import User, UserIdentity
from app.services import auth_service


def test_settings_load_wechat_and_smtp_values():
    """Load WeChat and SMTP config values from a settings payload."""
    settings = Settings.model_validate(
        {
            "database_url": "sqlite://",
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
    assert settings.wechat_app_secret == "wx-secret"
    assert settings.smtp_host == "smtp.example.com"
    assert settings.smtp_port == 587
    assert settings.smtp_from_email == "bot@example.com"


def test_verify_email_otp_marks_identity_verified(db_session):
    """Consume a valid OTP and verify the matching email identity."""
    user = User(status=0)
    db_session.add(user)
    db_session.flush()

    identity = UserIdentity(
        user_id=user.id,
        type="email",
        identifier="parent@example.com",
    )
    db_session.add(identity)
    db_session.commit()

    otp = auth_service.create_email_verification_otp(
        db_session,
        "parent@example.com",
        "123456",
    )
    db_session.commit()

    auth_service.verify_email_otp(db_session, "parent@example.com", "123456")

    db_session.refresh(identity)
    db_session.refresh(otp)
    assert identity.verified_at is not None
    assert otp.consumed_at is not None


def test_verify_email_otp_rejects_wrong_code(db_session):
    """Reject OTP verification when the code does not match."""
    auth_service.create_email_verification_otp(
        db_session,
        "parent@example.com",
        "123456",
    )
    db_session.commit()

    try:
        auth_service.verify_email_otp(db_session, "parent@example.com", "000000")
    except ValueError as exc:
        assert str(exc) == "Invalid or expired OTP code"
    else:
        raise AssertionError("Expected ValueError for an invalid OTP code")


def test_exchange_wechat_code_for_session_requires_config(monkeypatch):
    """Reject WeChat code exchange when app credentials are missing."""
    monkeypatch.setattr(auth_service.settings, "wechat_app_id", None)
    monkeypatch.setattr(auth_service.settings, "wechat_app_secret", None)

    with pytest.raises(auth_service.WechatConfigError) as exc_info:
        auth_service.exchange_wechat_code_for_session("test-code")

    assert str(exc_info.value) == "WeChat Mini Program login is not configured"


def test_exchange_wechat_code_for_session_maps_wechat_error(monkeypatch):
    """Map WeChat errcode responses to a dedicated API error."""

    class FakeResponse:
        """Provide a static JSON payload for WeChat API tests."""

        def raise_for_status(self) -> None:
            """Simulate a successful HTTP response."""
            return None

        def json(self) -> dict:
            """Return a WeChat API error payload."""
            return {"errcode": 40029, "errmsg": "invalid code"}

    def fake_get(*args, **kwargs):
        """Return a fake WeChat API response."""
        return FakeResponse()

    monkeypatch.setattr(auth_service.settings, "wechat_app_id", "wx-app-id")
    monkeypatch.setattr(auth_service.settings, "wechat_app_secret", "wx-secret")
    monkeypatch.setattr(auth_service.httpx, "get", fake_get)

    with pytest.raises(auth_service.WechatAPIError) as exc_info:
        auth_service.exchange_wechat_code_for_session("bad-code")

    assert exc_info.value.errcode == 40029
    assert exc_info.value.errmsg == "invalid code"


def test_exchange_wechat_code_for_session_maps_upstream_http_failure(monkeypatch):
    """Map HTTP transport failures to an upstream error."""

    def fake_get(*args, **kwargs):
        """Raise a request error from the HTTP client."""
        raise httpx.RequestError("network down", request=httpx.Request("GET", "https://example.com"))

    monkeypatch.setattr(auth_service.settings, "wechat_app_id", "wx-app-id")
    monkeypatch.setattr(auth_service.settings, "wechat_app_secret", "wx-secret")
    monkeypatch.setattr(auth_service.httpx, "get", fake_get)

    with pytest.raises(auth_service.WechatUpstreamError) as exc_info:
        auth_service.exchange_wechat_code_for_session("code")

    assert str(exc_info.value) == "Failed to exchange WeChat login code"


def test_get_or_create_user_by_wechat_session_prefers_unionid_and_binds_openid(db_session):
    """Use unionid as primary identity and bind openid to the same user."""
    user, is_new = auth_service.get_or_create_user_by_wechat_session(
        db_session,
        openid="openid-1",
        unionid="unionid-1",
    )

    identities = db_session.query(UserIdentity).filter(UserIdentity.user_id == user.id).all()

    assert is_new is True
    assert sorted(identity.identifier for identity in identities) == ["openid-1", "unionid-1"]


def test_get_or_create_user_by_wechat_session_reuses_openid_user_when_unionid_arrives(db_session):
    """Bind a later unionid to the existing openid user instead of creating a new user."""
    existing_user, _ = auth_service.get_or_create_user_by_identity(
        db_session,
        "wechat",
        "openid-1",
        provider="wechat_miniprogram_openid",
    )

    user, is_new = auth_service.get_or_create_user_by_wechat_session(
        db_session,
        openid="openid-1",
        unionid="unionid-1",
    )

    identities = db_session.query(UserIdentity).filter(UserIdentity.user_id == user.id).all()

    assert user.id == existing_user.id
    assert is_new is False
    assert sorted(identity.identifier for identity in identities) == ["openid-1", "unionid-1"]
