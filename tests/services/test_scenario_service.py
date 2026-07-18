"""Tests for scenario service folder initialization."""

from app.models import Family, Folder, ScenarioTemplate, User
from app.services.scenario_service import disable_scenario, enable_scenario


def test_enable_scenario_creates_default_folders_once(db_session):
    """Create missing top-level default folders without duplicating them on re-enable."""
    owner = User(status=0)
    db_session.add(owner)
    db_session.flush()

    family = Family(name="Scenario Test Family", owner_user_id=owner.id)
    db_session.add(family)
    db_session.flush()

    template = ScenarioTemplate(
        key="scenario-test",
        name="Scenario Test",
        version=1,
        definition={
            "default_folders": [
                {"zone": "shared", "name": "Shared Folder"},
                {"zone": "vault", "name": "Vault Folder"},
            ]
        },
    )
    db_session.add(template)
    db_session.commit()

    first_instance = enable_scenario(db_session, str(family.id), str(template.id))
    created_folders = db_session.query(Folder).filter(Folder.family_id == family.id).all()

    assert sorted((folder.zone, folder.name) for folder in created_folders) == [
        ("shared", "Shared Folder"),
        ("vault", "Vault Folder"),
    ]

    disable_scenario(db_session, first_instance)
    second_instance = enable_scenario(db_session, str(family.id), str(template.id))
    folders_after_reenable = db_session.query(Folder).filter(Folder.family_id == family.id).all()

    assert second_instance.id == first_instance.id
    assert sorted((folder.zone, folder.name) for folder in folders_after_reenable) == [
        ("shared", "Shared Folder"),
        ("vault", "Vault Folder"),
    ]
