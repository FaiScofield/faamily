"""Tests for family API role validation."""

from app.core.security import create_access_token
from app.models import Family, Membership, User


def test_update_member_role_rejects_legacy_child_role(client, db_session):
    """Return validation error when the API receives the removed child role."""
    owner = User(status=0)
    member_user = User(status=0)
    db_session.add_all([owner, member_user])
    db_session.flush()

    family = Family(name="API Family", owner_user_id=owner.id)
    db_session.add(family)
    db_session.flush()

    db_session.add_all(
        [
            Membership(
                family_id=family.id,
                user_id=owner.id,
                role="owner",
                status="active",
            ),
            Membership(
                family_id=family.id,
                user_id=member_user.id,
                role="member",
                status="active",
            ),
        ]
    )
    db_session.commit()

    token = create_access_token(str(owner.id))
    response = client.put(
        f"/v1/families/{family.id}/members/{member_user.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "child"},
    )

    assert response.status_code == 422
