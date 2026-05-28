"""Scenario API routes.

Endpoints:
- GET    /scenarios/templates              — List available scenario templates
- GET    /scenarios/templates/{id}         — Get template details
- POST   /scenarios/templates/seed         — Seed builtin templates
- GET    /families/{family_id}/scenarios    — List family's enabled scenarios
- POST   /families/{family_id}/scenarios    — Enable a scenario
- DELETE /families/{family_id}/scenarios/{id} — Disable a scenario
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import require_admin, require_any_role
from app.db import get_db
from app.models import Membership, ScenarioInstance, ScenarioTemplate, User
from app.services.scenario_service import (
    disable_scenario,
    enable_scenario,
    get_family_scenario,
    get_template,
    list_family_scenarios,
    list_templates,
    seed_templates,
)

router = APIRouter(tags=["scenarios"])


# ---------------------------------------------------------------------------
# Global: Template Catalog
# ---------------------------------------------------------------------------


@router.get("/scenarios/templates")
def list_scenario_templates(db: Session = Depends(get_db)):
    """List all available scenario templates."""
    templates = list_templates(db)
    return {
        "templates": [
            {
                "template_id": str(t.id),
                "key": t.key,
                "name": t.name,
                "version": t.version,
                "definition": t.definition,
            }
            for t in templates
        ]
    }


@router.get("/scenarios/templates/{template_id}")
def get_template_details(template_id: str, db: Session = Depends(get_db)):
    """Get details of a specific scenario template."""
    template = get_template(db, template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    return {
        "template_id": str(template.id),
        "key": template.key,
        "name": template.name,
        "version": template.version,
        "definition": template.definition,
    }


@router.post("/scenarios/templates/seed")
def seed_builtin_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Seed builtin scenario templates into the database.

    Only creates templates that don't already exist.
    """
    created = seed_templates(db)
    return {"detail": f"{created} template(s) created"}


# ---------------------------------------------------------------------------
# Family: Scenario Instances
# ---------------------------------------------------------------------------


@router.get("/families/{family_id}/scenarios")
def list_family_scenario_instances(
    family_id: str,
    membership: Membership = Depends(require_any_role),
    db: Session = Depends(get_db),
):
    """List all scenario instances enabled for a family."""
    instances = list_family_scenarios(db, family_id)
    return {
        "scenarios": [
            {
                "instance_id": str(i.id),
                "template_id": str(i.template_id),
                "status": i.status,
                "config": i.config,
                "enabled_at": i.enabled_at.isoformat(),
            }
            for i in instances
        ]
    }


@router.post("/families/{family_id}/scenarios", status_code=status.HTTP_201_CREATED)
def enable_scenario_endpoint(
    family_id: str,
    template_id: str,
    membership: Membership = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Enable a scenario template for this family (owner or admin only).

    The template_id should be provided as a query parameter.
    """
    try:
        instance = enable_scenario(db, family_id, template_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return {
        "instance_id": str(instance.id),
        "template_id": str(instance.template_id),
        "status": instance.status,
    }


@router.delete("/families/{family_id}/scenarios/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
def disable_scenario_endpoint(
    family_id: str,
    instance_id: str,
    membership: Membership = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Disable a scenario instance (owner or admin only)."""
    instance = get_family_scenario(db, family_id, instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario instance not found",
        )

    disable_scenario(db, instance)
    return None
