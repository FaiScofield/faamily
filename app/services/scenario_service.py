"""Scenario template service layer.

Manages predefined scenario templates (child learning, elder care,
baby care, appliance archive) and family-level scenario instances.
"""

from sqlalchemy.orm import Session

from app.models import ScenarioInstance, ScenarioTemplate


# ---------------------------------------------------------------------------
# Predefined Templates (seeded via migration or API)
# ---------------------------------------------------------------------------

BUILTIN_TEMPLATES: list[dict] = [
    {
        "key": "child_learning",
        "name": "儿童学习",
        "version": 1,
        "definition": {
            "description": "儿童学习场景：作业/阅读/练琴等任务与打卡，家长验收",
            "task_types": ["作业", "阅读", "练琴", "运动", "其他"],
            "default_folders": [
                {"zone": "shared", "name": "学习资料"},
                {"zone": "shared", "name": "作品展示"},
                {"zone": "vault", "name": "成绩单"},
            ],
            "features": ["daily_checkin", "parent_review", "streak_tracking"],
        },
    },
    {
        "key": "elder_care",
        "name": "老人照护",
        "version": 1,
        "definition": {
            "description": "老人照护场景：用药提醒、复诊安排、紧急联系人、重要资料归档",
            "task_types": ["用药提醒", "复诊", "体检", "日常照护"],
            "default_folders": [
                {"zone": "shared", "name": "健康记录"},
                {"zone": "shared", "name": "复诊安排"},
                {"zone": "vault", "name": "证件资料"},
                {"zone": "vault", "name": "保险单据"},
            ],
            "features": ["medication_reminder", "emergency_contacts", "appointment_tracking"],
        },
    },
    {
        "key": "baby_care",
        "name": "婴儿照看",
        "version": 1,
        "definition": {
            "description": "婴儿照看场景：喂养/睡眠/尿布/体温记录，疫苗/体检提醒与资料归档",
            "task_types": ["喂养记录", "睡眠记录", "换尿布", "体温记录", "疫苗", "体检"],
            "default_folders": [
                {"zone": "shared", "name": "日常记录"},
                {"zone": "shared", "name": "疫苗记录"},
                {"zone": "vault", "name": "出生证明"},
                {"zone": "vault", "name": "体检报告"},
            ],
            "features": ["daily_log", "vaccine_schedule", "growth_tracking"],
        },
    },
    {
        "key": "appliance_archive",
        "name": "大件归档",
        "version": 1,
        "definition": {
            "description": "大件归档场景：家电家具购买记录、保修、说明书、铭牌照片归档",
            "task_types": ["保修到期提醒", "年检", "保养"],
            "default_folders": [
                {"zone": "shared", "name": "家电"},
                {"zone": "shared", "name": "家具"},
                {"zone": "shared", "name": "电子产品"},
                {"zone": "vault", "name": "发票收据"},
                {"zone": "vault", "name": "合同凭证"},
            ],
            "features": ["warranty_tracking", "purchase_record"],
        },
    },
    {
        "key": "pet_care",
        "name": "宠物照料",
        "version": 1,
        "definition": {
            "description": "宠物照料场景：喂养/遛狗/驱虫/疫苗记录，宠物档案与健康资料归档",
            "task_types": ["喂养", "遛狗/放风", "驱虫", "疫苗", "洗澡", "体检"],
            "default_folders": [
                {"zone": "shared", "name": "日常记录"},
                {"zone": "shared", "name": "宠物照片"},
                {"zone": "shared", "name": "疫苗记录"},
                {"zone": "vault", "name": "宠物证件"},
                {"zone": "vault", "name": "医疗报告"},
            ],
            "features": ["daily_log", "vaccine_schedule", "pet_profile"],
        },
    },
]


def seed_templates(db: Session) -> int:
    """Seed builtin templates into the database.

    Only creates templates that don't already exist (by key + version).

    Args:
        db: Database session.

    Returns:
        Number of templates created.
    """
    created = 0
    for tmpl in BUILTIN_TEMPLATES:
        existing = db.query(ScenarioTemplate).filter(
            ScenarioTemplate.key == tmpl["key"],
            ScenarioTemplate.version == tmpl["version"],
        ).first()

        if not existing:
            template = ScenarioTemplate(
                key=tmpl["key"],
                name=tmpl["name"],
                version=tmpl["version"],
                definition=tmpl["definition"],
            )
            db.add(template)
            created += 1

    if created > 0:
        db.commit()
    return created


def list_templates(db: Session) -> list[ScenarioTemplate]:
    """List all available scenario templates (latest version per key)."""
    # Get latest version for each key
    from sqlalchemy import func

    subquery = (
        db.query(
            ScenarioTemplate.key,
            func.max(ScenarioTemplate.version).label("max_version"),
        )
        .group_by(ScenarioTemplate.key)
        .subquery()
    )

    templates = (
        db.query(ScenarioTemplate)
        .join(
            subquery,
            (ScenarioTemplate.key == subquery.c.key)
            & (ScenarioTemplate.version == subquery.c.max_version),
        )
        .all()
    )
    return templates


def get_template(db: Session, template_id: str) -> ScenarioTemplate | None:
    """Get a template by ID."""
    return db.query(ScenarioTemplate).filter(ScenarioTemplate.id == template_id).first()


def get_template_by_key(db: Session, key: str) -> ScenarioTemplate | None:
    """Get the latest version of a template by key."""
    from sqlalchemy import func

    template = (
        db.query(ScenarioTemplate)
        .filter(ScenarioTemplate.key == key)
        .order_by(ScenarioTemplate.version.desc())
        .first()
    )
    return template


# ---------------------------------------------------------------------------
# Scenario Instances (family-level)
# ---------------------------------------------------------------------------


def enable_scenario(
    db: Session,
    family_id: str,
    template_id: str,
    config: dict | None = None,
) -> ScenarioInstance:
    """Enable a scenario template for a family.

    Args:
        db: Database session.
        family_id: UUID of the family.
        template_id: UUID of the template to enable.
        config: Optional family-specific configuration overrides.

    Returns:
        The created ScenarioInstance object.

    Raises:
        ValueError: If scenario is already enabled for this family.
    """
    existing = db.query(ScenarioInstance).filter(
        ScenarioInstance.family_id == family_id,
        ScenarioInstance.template_id == template_id,
    ).first()

    if existing:
        if existing.status == "enabled":
            raise ValueError("This scenario is already enabled for this family")
        # Re-enable disabled instance
        existing.status = "enabled"
        existing.config = config or existing.config
        db.commit()
        db.refresh(existing)
        return existing

    instance = ScenarioInstance(
        family_id=family_id,
        template_id=template_id,
        status="enabled",
        config=config or {},
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def disable_scenario(db: Session, instance: ScenarioInstance) -> None:
    """Disable a scenario instance for a family."""
    instance.status = "disabled"
    db.commit()


def list_family_scenarios(db: Session, family_id: str) -> list[ScenarioInstance]:
    """List all scenario instances for a family."""
    return db.query(ScenarioInstance).filter(
        ScenarioInstance.family_id == family_id,
    ).all()


def get_family_scenario(db: Session, family_id: str, instance_id: str) -> ScenarioInstance | None:
    """Get a specific scenario instance."""
    return db.query(ScenarioInstance).filter(
        ScenarioInstance.id == instance_id,
        ScenarioInstance.family_id == family_id,
    ).first()
