"""Verify db/schema.sql matches the SQLAlchemy ORM models.

Compares table names and column names (not types) for every ORM model.
Run: python scripts/check_schema_sync.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = REPO_ROOT / "db" / "schema.sql"
MODELS_PY = REPO_ROOT / "app" / "models" / "__init__.py"


def parse_schema_tables() -> dict[str, set[str]]:
    """Extract {table: {columns}} from db/schema.sql.

    Uses balanced-paren scanning so that nested parentheses inside
    CHECK/UNIQUE constraints do not truncate the table body.
    """
    text = SCHEMA_SQL.read_text(encoding="utf-8")
    tables: dict[str, set[str]] = {}

    for match in re.finditer(r"create table if not exists (\w+)\s*\(", text):
        table = match.group(1)
        start = match.end()  # position right after the opening paren

        depth = 1
        i = start
        while i < len(text) and depth > 0:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1

        body = text[start : i - 1]
        cols: set[str] = set()
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("--"):
                continue
            # Skip constraint definitions. Note: match on word boundaries —
            # a bare "check" prefix would also swallow the column "checksum".
            if re.match(
                r"^(constraint|primary\s+key|unique|check|foreign\s+key)\b",
                line,
                re.IGNORECASE,
            ):
                continue
            token = line.split()[0].rstrip(",")
            if token and re.match(r"^[a-z_][a-z0-9_]*$", token):
                cols.add(token)
        tables[table] = cols
    return tables


def parse_orm_tables() -> dict[str, set[str]]:
    """Extract {table: {columns}} from the ORM model definitions.

    Only `mapped_column` attributes count as columns — `relationship()`
    attributes are excluded. TimestampMixin contributes created_at/updated_at.
    """
    text = MODELS_PY.read_text(encoding="utf-8")
    tables: dict[str, set[str]] = {}

    # Split into class blocks first so we can see the class declaration line
    for block in re.split(r"\nclass ", text)[1:]:
        cls_match = re.match(r"(\w+)\(([^)]*)\)", block)
        if not cls_match:
            continue
        cls_name, bases = cls_match.group(1), cls_match.group(2)

        tm = re.search(r'__tablename__ = "(\w+)"', block)
        if not tm:
            continue
        table = tm.group(1)

        cols: set[str] = set()
        for attr in re.finditer(
            r"^\s{4}(\w+):\s*Mapped\[[^\]]+\]\s*=\s*mapped_column\(", block, re.MULTILINE
        ):
            cols.add(attr.group(1))

        # TimestampMixin provides created_at / updated_at
        if "TimestampMixin" in bases:
            cols.update({"created_at", "updated_at"})

        tables[table] = cols
    return tables


def main() -> int:
    schema = parse_schema_tables()
    orm = parse_orm_tables()

    problems: list[str] = []

    missing_tables = sorted(set(orm) - set(schema))
    extra_tables = sorted(set(schema) - set(orm))
    for t in missing_tables:
        problems.append(f"schema.sql 缺少表: {t}")
    for t in extra_tables:
        problems.append(f"schema.sql 多出表（ORM 中没有）: {t}")

    for table in sorted(set(orm) & set(schema)):
        missing_cols = sorted(orm[table] - schema[table])
        extra_cols = sorted(schema[table] - orm[table])
        for c in missing_cols:
            problems.append(f"{table} 缺少列: {c}")
        for c in extra_cols:
            problems.append(f"{table} 多出列: {c}")

    if problems:
        print(f"❌ schema.sql 与 ORM 不一致（{len(problems)} 项）:\n")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"✅ schema.sql 与 ORM 一致（{len(orm)} 张表）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
