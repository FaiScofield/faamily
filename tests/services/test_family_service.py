"""Tests for family service role updates."""

import pytest

from app.models import Family, Membership, User
from app.services.family_service import update_member_role


def test_update_member_role_rejects_legacy_child_role(db_session):
    """Reject the removed legacy child role in service-level updates."""
    owner = User(status=0)
    member_user = User(status=0)
    db_session.add_all([owner, member_user])
    db_session.flush()

    family = Family(name="Role Test Family", owner_user_id=owner.id)
    db_session.add(family)
    db_session.flush()

    membership = Membership(
        family_id=family.id,
        user_id=member_user.id,
        role="member",
        status="active",
    )
    db_session.add(membership)
    db_session.commit()

    with pytest.raises(ValueError, match="Role must be one of: owner, admin, member"):
        update_member_role(db_session, membership, "child")
