"""Tests for vault access control.

Covers the second-factor flow: requesting an email OTP, exchanging it for a
vault session, and the requirement that vault resources stay inaccessible
without a valid session.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import create_access_token
from app.models import (
    Family,
    File,
    Folder,
    Membership,
    User,
    UserIdentity,
    VaultEmailOtp,
    VaultSession,
)
from app.services.document_service import (
    MAX_OTP_ATTEMPTS,
    create_vault_otp,
    get_verified_email,
    verify_vault_otp,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def vault_setup(db_session):
    """Create a user with a verified email, a family and an owner membership."""
    owner = User(status=0)
    db_session.add(owner)
    db_session.flush()

    family = Family(name="Vault Family", owner_user_id=owner.id)
    db_session.add(family)
    db_session.flush()

    db_session.add(
        Membership(
            family_id=family.id,
            user_id=owner.id,
            role="owner",
            status="active",
        )
    )
    db_session.add(
        UserIdentity(
            user_id=owner.id,
            type="email",
            identifier="owner@example.com",
            verified_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    token = create_access_token(str(owner.id))
    headers = {"Authorization": f"Bearer {token}"}
    return {
        "user": owner,
        "family": family,
        "headers": headers,
        "base": f"/v1/families/{family.id}/documents",
    }


# ---------------------------------------------------------------------------
# Email ownership
# ---------------------------------------------------------------------------


def test_get_verified_email_requires_bound_and_verified_identity(db_session):
    """Only an email the user bound AND verified is accepted."""
    user = User(status=0)
    db_session.add(user)
    db_session.flush()

    db_session.add(
        UserIdentity(
            user_id=user.id,
            type="email",
            identifier="bound@example.com",
            verified_at=None,  # not verified yet
        )
    )
    db_session.commit()

    assert get_verified_email(db_session, str(user.id), "bound@example.com") is None

    identity = db_session.query(UserIdentity).filter_by(identifier="bound@example.com").first()
    identity.verified_at = datetime.now(timezone.utc)
    db_session.commit()

    assert get_verified_email(db_session, str(user.id), "bound@example.com") == (
        "bound@example.com"
    )


def test_get_verified_email_rejects_email_of_another_user(db_session, vault_setup):
    """An email bound to a different account is not accepted."""
    other = User(status=0)
    db_session.add(other)
    db_session.flush()
    db_session.add(
        UserIdentity(
            user_id=other.id,
            type="email",
            identifier="other@example.com",
            verified_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    result = get_verified_email(
        db_session, str(vault_setup["user"].id), "other@example.com"
    )
    assert result is None


# ---------------------------------------------------------------------------
# OTP attempt limiting
# ---------------------------------------------------------------------------


def test_verify_vault_otp_rejects_wrong_code(db_session, vault_setup):
    """A wrong code does not open the vault."""
    user = vault_setup["user"]
    create_vault_otp(db_session, str(user.id), "owner@example.com")

    assert not verify_vault_otp(
        db_session, str(user.id), "owner@example.com", "000000"
    )


def test_verify_vault_otp_accepts_correct_code(db_session, vault_setup):
    """The issued code opens the vault exactly once."""
    user = vault_setup["user"]
    code = create_vault_otp(db_session, str(user.id), "owner@example.com")

    assert verify_vault_otp(db_session, str(user.id), "owner@example.com", code)
    # A second use of the same code is rejected
    assert not verify_vault_otp(db_session, str(user.id), "owner@example.com", code)


def test_verify_vault_otp_blocks_after_max_attempts(db_session, vault_setup):
    """Brute-forcing is bounded — the code dies after MAX_OTP_ATTEMPTS failures."""
    user = vault_setup["user"]
    code = create_vault_otp(db_session, str(user.id), "owner@example.com")

    for _ in range(MAX_OTP_ATTEMPTS):
        assert not verify_vault_otp(
            db_session, str(user.id), "owner@example.com", "999999"
        )

    # Even the correct code no longer works
    assert not verify_vault_otp(db_session, str(user.id), "owner@example.com", code)


def test_create_vault_otp_invalidates_previous_code(db_session, vault_setup):
    """Requesting a new code invalidates the previous one."""
    user = vault_setup["user"]
    first = create_vault_otp(db_session, str(user.id), "owner@example.com")
    second = create_vault_otp(db_session, str(user.id), "owner@example.com")

    assert not verify_vault_otp(db_session, str(user.id), "owner@example.com", first)
    assert verify_vault_otp(db_session, str(user.id), "owner@example.com", second)


# ---------------------------------------------------------------------------
# API: no plaintext code in the response
# ---------------------------------------------------------------------------


def test_vault_otp_response_never_contains_the_code(client, db_session, vault_setup, monkeypatch):
    """The OTP code must not be echoed back to the client."""
    sent = {}

    def fake_send(recipient, code, subject, body):
        sent["recipient"] = recipient
        sent["code"] = code

    monkeypatch.setattr("app.api.documents.send_otp_email", fake_send)

    response = client.post(
        f"{vault_setup['base']}/vault/otp",
        headers=vault_setup["headers"],
        json={"email": "owner@example.com"},
    )

    assert response.status_code == 200
    assert sent["code"], "the code should have been sent by email"
    assert sent["code"] not in response.text
    assert "_dev_otp_code" not in response.text


def test_vault_otp_rejects_email_not_owned_by_user(client, vault_setup):
    """An email the user has not bound and verified is refused."""
    response = client.post(
        f"{vault_setup['base']}/vault/otp",
        headers=vault_setup["headers"],
        json={"email": "attacker@example.com"},
    )

    assert response.status_code == 400
    assert "verified identity" in response.json()["detail"]


def test_vault_otp_reports_smtp_unavailable(client, vault_setup, monkeypatch):
    """Without SMTP the endpoint fails loudly instead of leaking the code."""

    def fake_send(*args, **kwargs):
        raise RuntimeError("SMTP is not configured")

    monkeypatch.setattr("app.api.documents.send_otp_email", fake_send)

    response = client.post(
        f"{vault_setup['base']}/vault/otp",
        headers=vault_setup["headers"],
        json={"email": "owner@example.com"},
    )

    assert response.status_code == 503
    assert "SMTP" in response.json()["detail"]


# ---------------------------------------------------------------------------
# API: vault resources require a session
# ---------------------------------------------------------------------------


def test_vault_files_list_requires_session(client, db_session, vault_setup):
    """Without a vault session, vault files are unreachable."""
    db_session.add(
        File(
            family_id=vault_setup["family"].id,
            zone="vault",
            owner_type="document",
            uploader_user_id=vault_setup["user"].id,
            filename="secret.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            storage_key="vault/secret.pdf",
        )
    )
    db_session.commit()

    response = client.get(
        f"{vault_setup['base']}/files?zone=vault",
        headers=vault_setup["headers"],
    )

    assert response.status_code == 403
    assert "Vault access" in response.json()["detail"]


def test_vault_files_hidden_when_zone_omitted(client, db_session, vault_setup):
    """Omitting the zone must not leak vault files."""
    db_session.add(
        File(
            family_id=vault_setup["family"].id,
            zone="vault",
            owner_type="document",
            uploader_user_id=vault_setup["user"].id,
            filename="secret.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            storage_key="vault/secret.pdf",
        )
    )
    db_session.commit()

    response = client.get(
        f"{vault_setup['base']}/files",
        headers=vault_setup["headers"],
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_vault_files_visible_with_valid_session(client, db_session, vault_setup):
    """A valid vault session unlocks the vault."""
    db_session.add(
        File(
            family_id=vault_setup["family"].id,
            zone="vault",
            owner_type="document",
            uploader_user_id=vault_setup["user"].id,
            filename="secret.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            storage_key="vault/secret.pdf",
        )
    )
    db_session.add(
        VaultSession(
            user_id=vault_setup["user"].id,
            family_id=vault_setup["family"].id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
    )
    db_session.commit()

    response = client.get(
        f"{vault_setup['base']}/files?zone=vault",
        headers=vault_setup["headers"],
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_expired_vault_session_does_not_unlock(client, db_session, vault_setup):
    """An expired session is as good as none."""
    db_session.add(
        File(
            family_id=vault_setup["family"].id,
            zone="vault",
            owner_type="document",
            uploader_user_id=vault_setup["user"].id,
            filename="secret.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            storage_key="vault/secret.pdf",
        )
    )
    db_session.add(
        VaultSession(
            user_id=vault_setup["user"].id,
            family_id=vault_setup["family"].id,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    db_session.commit()

    response = client.get(
        f"{vault_setup['base']}/files?zone=vault",
        headers=vault_setup["headers"],
    )

    assert response.status_code == 403


def test_creating_vault_folder_requires_session(client, vault_setup):
    """Creating a folder inside the vault needs a vault session."""
    response = client.post(
        f"{vault_setup['base']}/folders",
        headers=vault_setup["headers"],
        json={"zone": "vault", "name": "证件"},
    )

    assert response.status_code == 403


def test_shared_folder_still_works_without_session(client, vault_setup):
    """The shared zone is unaffected by vault protection."""
    response = client.post(
        f"{vault_setup['base']}/folders",
        headers=vault_setup["headers"],
        json={"zone": "shared", "name": "说明书"},
    )

    assert response.status_code == 201


def test_upload_into_vault_folder_requires_session(client, db_session, vault_setup):
    """A file cannot be smuggled into a vault folder without a session."""
    vault_folder = Folder(
        family_id=vault_setup["family"].id,
        zone="vault",
        name="银行卡",
    )
    db_session.add(vault_folder)
    db_session.commit()

    response = client.post(
        f"{vault_setup['base']}/files",
        headers=vault_setup["headers"],
        json={
            "filename": "card.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 100,
            "storage_key": "vault/card.pdf",
            "folder_id": str(vault_folder.id),
        },
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# OTP table integrity
# ---------------------------------------------------------------------------


def test_vault_otp_records_are_hashed_not_plaintext(db_session, vault_setup):
    """The stored OTP is a hash, never the plain code."""
    user = vault_setup["user"]
    code = create_vault_otp(db_session, str(user.id), "owner@example.com")

    record = (
        db_session.query(VaultEmailOtp)
        .filter(VaultEmailOtp.user_id == user.id)
        .order_by(VaultEmailOtp.created_at.desc())
        .first()
    )

    assert record is not None
    assert record.code_hash != code
    assert code not in record.code_hash
