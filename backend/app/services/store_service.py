from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "harmonization.db"
APP_SETTINGS_KEY = "app_settings_json"
DEFAULT_APP_SETTINGS: dict[str, Any] = {
    "workspace_identity": {
        "default_project": "",
        "timezone": "UTC",
        "date_format": "YYYY-MM-DD",
        "display_name": "",
        "email": "name@zalaris.com",
        "role": "developer",
        "team_owner_map": {},
    },
    "rule_engine_defaults": {
        "default_severity": "WARNING",
        "auto_approve_confidence": 0.85,
        "duplicate_similarity_threshold": 0.9,
        "default_pack_by_rule_type": {},
    },
    "validation_scan_behavior": {
        "auto_scan_on_upload": True,
        "max_rules_per_extraction": 10,
        "validation_mode": "strict",
        "ignore_patterns": [],
    },
    "ai_assistant_controls": {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "model_api_key": "",
        "prompt_style": "balanced",
        "max_tokens": 1200,
        "response_length": "medium",
        "log_suggestions": True,
    },
    "dashboard_preferences": {
        "default_date_range_days": 30,
        "default_grouping": "developer",
        "kpi_cards": {
            "open_violations": True,
            "fixed_rate": True,
            "top_rule_packs": True,
            "active_developers": True,
        },
        "auto_refresh_interval_sec": 0,
    },
    "notifications": {
        "channels": ["email"],
        "triggers": ["new_high_severity", "failed_validation"],
        "digest_frequency": "daily",
    },
    "security_compliance": {
        "retention_days": 180,
        "pii_masking": True,
        "audit_log_export": True,
        "settings_change_roles": ["admin"],
    },
    "integrations": {
        "sap_endpoint": "",
        "ticketing_provider": "",
        "ci_hook_url": "",
        "webhook_secret": "",
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except Exception:
        return None


def _resolve_date_bounds(start_date: str | None, end_date: str | None) -> tuple[str | None, str | None]:
    start = _normalize_iso_date(start_date)
    end = _normalize_iso_date(end_date)
    if start and end and start > end:
        return end, start
    return start, end


def _get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                members_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rules (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                yaml_text TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                source_type TEXT NOT NULL,
                created_by TEXT NOT NULL,
                duplicate_of TEXT,
                similarity REAL,
                source_snippet TEXT,
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS packs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                project_id TEXT,
                rules_json TEXT NOT NULL,
                rule_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS wizards (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                total_steps INTEGER NOT NULL,
                project_id TEXT,
                rule_pack TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS wizard_steps (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                wizard_id TEXT NOT NULL,
                step_no INTEGER NOT NULL,
                rule_id TEXT NOT NULL,
                yaml_text TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dashboard_violations (
                id TEXT PRIMARY KEY,
                rule_pack TEXT NOT NULL,
                object_name TEXT NOT NULL,
                transport TEXT NOT NULL,
                developer TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Not Fixed',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rule_pack_options (
                id TEXT PRIMARY KEY,
                rule_type TEXT NOT NULL,
                pack_name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ui_config (
                config_key TEXT PRIMARY KEY,
                config_value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_rules_project ON rules(project_id);
            CREATE INDEX IF NOT EXISTS idx_rules_created_at ON rules(created_at);
            CREATE INDEX IF NOT EXISTS idx_rules_rule_id ON rules(rule_id);
            CREATE INDEX IF NOT EXISTS idx_dashboard_violations_created ON dashboard_violations(created_at);
            CREATE INDEX IF NOT EXISTS idx_wizard_steps_wizard ON wizard_steps(wizard_id);
            """
        )

        # Backward-compatible migration for older DBs.
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(rules)").fetchall()
        }
        if "rule_pack" not in cols:
            conn.execute("ALTER TABLE rules ADD COLUMN rule_pack TEXT")

        wizard_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(wizards)").fetchall()
        }
        if "rule_pack" not in wizard_cols:
            conn.execute("ALTER TABLE wizards ADD COLUMN rule_pack TEXT")

        violation_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(dashboard_violations)").fetchall()
        }
        if "status" not in violation_cols:
            conn.execute("ALTER TABLE dashboard_violations ADD COLUMN status TEXT NOT NULL DEFAULT 'Not Fixed'")
        conn.execute(
            """
            UPDATE dashboard_violations
            SET status = CASE
                WHEN LOWER(COALESCE(status, '')) = 'fixed' THEN 'Fixed'
                ELSE 'Not Fixed'
            END
            """
        )


_init_db()


def _slugify(name: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return text or "project"


def _derive_rule_fields(rule: dict[str, Any]) -> dict[str, Any]:
    derived = {
        "rule_id": "unknown.rule",
        "category": "code",
        "severity": "MAJOR",
        "confidence": 0.0,
        "yaml_text": "",
        "source_snippet": None,
    }
    if not isinstance(rule, dict):
        derived["yaml_text"] = yaml.safe_dump({"value": str(rule)})
        return derived

    yaml_text = rule.get("yaml")
    parsed: dict[str, Any] = {}
    if isinstance(yaml_text, str) and yaml_text.strip():
        derived["yaml_text"] = yaml_text
        try:
            loaded = yaml.safe_load(yaml_text)
            if isinstance(loaded, dict):
                parsed = loaded
        except Exception:
            parsed = {}
    else:
        parsed = rule
        derived["yaml_text"] = yaml.safe_dump(rule, sort_keys=False)

    derived["rule_id"] = str(parsed.get("id") or rule.get("_id") or "unknown.rule")
    derived["category"] = str(parsed.get("type") or rule.get("category") or "code").lower()
    derived["severity"] = str(parsed.get("severity") or rule.get("_severity") or "MAJOR").upper()
    derived["source_snippet"] = rule.get("source_snippet")

    try:
        derived["confidence"] = float(rule.get("confidence", parsed.get("confidence", 0.0)) or 0.0)
    except Exception:
        derived["confidence"] = 0.0
    return derived


def _record_dashboard_violation(
    rule_pack: str,
    object_name: str,
    developer: str,
    severity: str,
) -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO dashboard_violations (
                id, rule_pack, object_name, transport, developer, severity, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"vio-{uuid.uuid4().hex[:12]}",
                rule_pack,
                object_name,
                f"AUTO{uuid.uuid4().hex[:8].upper()}",
                developer or "unknown",
                severity.upper(),
                _now_iso(),
            ),
        )


def list_projects() -> list[dict[str, Any]]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, description, members_json FROM projects ORDER BY name"
        ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "members": json.loads(row["members_json"] or "[]"),
        }
        for row in rows
    ]


def create_project(name: str, description: str | None, members: list[dict[str, str]]) -> dict[str, Any]:
    project_id = f"{_slugify(name)}-{uuid.uuid4().hex[:6]}"
    member_list = [
        {
            "name": member.get("name", "").strip(),
            "email": member.get("email", "").strip(),
            "role": member.get("role", "developer").strip(),
        }
        for member in members
    ]
    project = {
        "id": project_id,
        "name": name.strip(),
        "description": description.strip() if isinstance(description, str) and description.strip() else None,
        "members": member_list,
    }
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, description, members_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project["id"],
                project["name"],
                project["description"],
                json.dumps(project["members"]),
                _now_iso(),
            ),
        )
    return project


def update_project(
    project_id: str,
    name: str,
    description: str | None,
    members: list[dict[str, str]],
) -> dict[str, Any] | None:
    member_list = [
        {
            "name": member.get("name", "").strip(),
            "email": member.get("email", "").strip(),
            "role": member.get("role", "developer").strip(),
        }
        for member in members
    ]
    project = {
        "id": project_id.strip(),
        "name": name.strip(),
        "description": description.strip() if isinstance(description, str) and description.strip() else None,
        "members": member_list,
    }
    with _get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM projects WHERE id = ?",
            (project["id"],),
        ).fetchone()
        if not existing:
            return None
        conn.execute(
            """
            UPDATE projects
            SET name = ?, description = ?, members_json = ?
            WHERE id = ?
            """,
            (
                project["name"],
                project["description"],
                json.dumps(project["members"]),
                project["id"],
            ),
        )
    return project


def add_rule_for_project(
    project_id: str,
    rule: dict[str, Any],
    status: str = "extracted",
    source_type: str = "text",
    created_by: str = "system",
) -> None:
    # Persist only user-approved lifecycle states.
    persisted_statuses = {"saved", "approved", "edited"}
    normalized_status = str(status or "").lower()
    if normalized_status not in persisted_statuses:
        return

    with _get_conn() as conn:
        project = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return

        derived = _derive_rule_fields(rule)
        rule_pack = str(rule.get("rule_pack") or "generic").strip()
        conn.execute(
            """
            INSERT INTO rules (
                project_id, rule_id, yaml_text, category, severity, confidence,
                status, source_type, created_by, duplicate_of, similarity,
                source_snippet, raw_json, created_at, rule_pack
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                derived["rule_id"],
                derived["yaml_text"],
                derived["category"],
                derived["severity"],
                derived["confidence"],
                normalized_status,
                source_type,
                created_by,
                rule.get("duplicate_of"),
                rule.get("similarity"),
                derived["source_snippet"],
                json.dumps(rule),
                _now_iso(),
                rule_pack,
            ),
        )

    if normalized_status == "edited":
        _record_dashboard_violation(
            rule_pack=str(rule.get("rule_pack") or "generic"),
            object_name=str(derived["rule_id"]),
            developer=created_by,
            severity=str(derived["severity"]),
        )


def _ensure_wizard_fields(
    rule_obj: dict[str, Any],
    wizard_id: str,
    wizard_name: str,
    wizard_description: str,
    total_steps: int,
    step_no: int,
) -> dict[str, Any]:
    wizard_block = rule_obj.get("wizard")
    if not isinstance(wizard_block, dict):
        wizard_block = {}

    step_title = str(wizard_block.get("step_title") or rule_obj.get("title") or f"Step {step_no}").strip()
    step_description = str(
        wizard_block.get("step_description") or rule_obj.get("description") or "No description provided."
    ).strip()

    wizard_block.update(
        {
            "wizard_id": wizard_id,
            "wizard_name": wizard_name,
            "wizard_description": wizard_description,
            "total_steps": int(total_steps),
            "step_no": int(step_no),
            "step_title": step_title,
            "step_description": step_description,
        }
    )

    rule_obj["wizard"] = wizard_block
    rule_obj["type"] = "wizard"
    rule_obj["title"] = rule_obj.get("title") or step_title
    rule_obj["description"] = rule_obj.get("description") or step_description
    rule_obj["id"] = rule_obj.get("id") or f"wizard.{_slugify(wizard_name)}.step.{step_no}"
    return rule_obj


def save_wizard(
    project_id: str,
    wizard_name: str,
    wizard_description: str,
    total_steps: int,
    steps: list[dict[str, Any]],
    created_by: str,
    rule_pack: str | None = None,
) -> dict[str, Any]:
    if not project_id:
        raise ValueError("project_id is required")
    if not wizard_name or not wizard_name.strip():
        raise ValueError("wizard_name is required")
    if not wizard_description or not wizard_description.strip():
        raise ValueError("wizard_description is required")
    if total_steps < 1:
        raise ValueError("total_steps must be >= 1")
    if not steps:
        raise ValueError("wizard steps are required")

    wizard_id = f"wiz-{uuid.uuid4().hex[:10]}"
    now = _now_iso()
    normalized_pack = str(rule_pack or "wizard").strip() or "wizard"

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO wizards (id, name, description, total_steps, project_id, rule_pack, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                wizard_id,
                wizard_name.strip(),
                wizard_description.strip(),
                int(total_steps),
                project_id,
                normalized_pack,
                created_by,
                now,
            ),
        )

    seen_steps: set[int] = set()
    saved_steps = 0
    for step in steps:
        yaml_text = str(step.get("yaml") or "").strip()
        if not yaml_text:
            raise ValueError("wizard step yaml is missing")

        try:
            parsed = yaml.safe_load(yaml_text)
        except Exception as exc:
            raise ValueError(f"invalid wizard step yaml: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("wizard step yaml must be a mapping")

        wizard_block = parsed.get("wizard")
        if not isinstance(wizard_block, dict):
            raise ValueError("wizard block missing in step yaml")
        raw_step_no = wizard_block.get("step_no")
        try:
            step_no = int(raw_step_no)
        except Exception as exc:
            raise ValueError("wizard step_no missing or invalid") from exc
        if step_no < 1:
            raise ValueError("wizard step_no must be >= 1")
        if step_no in seen_steps:
            raise ValueError(f"duplicate wizard step_no {step_no}")
        seen_steps.add(step_no)

        parsed = _ensure_wizard_fields(
            parsed,
            wizard_id=wizard_id,
            wizard_name=wizard_name.strip(),
            wizard_description=wizard_description.strip(),
            total_steps=total_steps,
            step_no=step_no,
        )
        updated_yaml = yaml.safe_dump(parsed, sort_keys=False, width=120)
        rule_id = str(parsed.get("id") or f"wizard.{_slugify(wizard_name)}.step.{step_no}")

        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO wizard_steps (wizard_id, step_no, rule_id, yaml_text, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (wizard_id, step_no, rule_id, updated_yaml, created_by, now),
            )

        add_rule_for_project(
            project_id,
            {
                "yaml": updated_yaml,
                "confidence": step.get("confidence", parsed.get("confidence", 0.7)),
                "category": "wizard",
                "_id": rule_id,
                "_severity": parsed.get("severity"),
                "rule_pack": normalized_pack,
            },
            status="saved",
            source_type="wizard",
            created_by=created_by,
        )
        saved_steps += 1

    return {
        "wizard_id": wizard_id,
        "saved_steps": saved_steps,
        "total_steps": int(total_steps),
    }


def get_rules_for_project(project_id: str, created_by: str | None = None) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        sql = """
            SELECT rule_id, yaml_text, confidence, category, severity, duplicate_of,
                   similarity, source_snippet, status, rule_pack
            FROM rules
            WHERE project_id = ?
              AND LOWER(status) IN ('saved', 'approved', 'edited')
        """
        params: list[Any] = [project_id]
        if created_by:
            sql += " AND created_by = ?"
            params.append(created_by)
        sql += " ORDER BY row_id DESC"
        rows = conn.execute(sql, tuple(params)).fetchall()

    return [
        {
            "yaml": row["yaml_text"],
            "confidence": row["confidence"],
            "category": row["category"],
            "_id": row["rule_id"],
            "_severity": row["severity"],
            "duplicate_of": row["duplicate_of"],
            "similarity": row["similarity"],
            "source_snippet": row["source_snippet"],
            "rule_pack": row["rule_pack"] or "generic",
            "status": "approved" if str(row["status"]).lower() in {"approved", "saved"} else row["status"],
        }
        for row in rows
    ]


def save_rule_pack(
    name: str,
    status: str,
    project_id: str | None,
    rules: list[dict[str, Any]],
    created_by: str = "name@zalaris.com",
) -> dict[str, Any]:
    pack = {
        "id": f"pack-{uuid.uuid4().hex[:8]}",
        "name": name.strip(),
        "status": status,
        "project_id": project_id,
        "rules": rules,
        "rule_count": len(rules),
        "created_at": _now_iso(),
    }
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO packs (id, name, status, project_id, rules_json, rule_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pack["id"],
                pack["name"],
                pack["status"],
                pack["project_id"],
                json.dumps(pack["rules"]),
                pack["rule_count"],
                pack["created_at"],
            ),
        )

    if project_id:
        for rule in rules:
            normalized_rule = rule
            if isinstance(rule, dict) and isinstance(rule.get("parsed"), dict):
                normalized_rule = {
                    **rule["parsed"],
                    "yaml": rule.get("yaml"),
                    "confidence": rule.get("confidence"),
                    "category": rule.get("category"),
                    "_id": rule.get("_id"),
                    "_severity": rule.get("_severity"),
                }
            add_rule_for_project(
                project_id,
                {**normalized_rule, "rule_pack": name},
                status="saved",
                source_type="pack",
                created_by=created_by,
            )

    return pack


def list_rule_packs(created_by: str | None = None) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        explicit_rows = conn.execute(
            """
            SELECT name, status, project_id, rule_count, created_at
            FROM packs
            ORDER BY created_at DESC
            """
        ).fetchall()
        grouped_sql = """
            SELECT COALESCE(rule_pack, 'generic') AS name,
                   COUNT(*) AS rule_count,
                   MAX(created_at) AS updated_at
            FROM rules
            WHERE LOWER(status) IN ('saved', 'approved', 'edited')
              AND LOWER(category) <> 'wizard'
        """
        grouped_params: list[Any] = []
        if created_by:
            grouped_sql += " AND created_by = ?"
            grouped_params.append(created_by)
        grouped_sql += """
            GROUP BY COALESCE(rule_pack, 'generic')
            ORDER BY updated_at DESC
        """
        grouped_rule_rows = conn.execute(grouped_sql, tuple(grouped_params)).fetchall()
        wizard_sql = """
            SELECT COALESCE(w.rule_pack, 'wizard') AS name,
                   COUNT(ws.row_id) AS wizard_count,
                   MAX(w.created_at) AS updated_at
            FROM wizards w
            LEFT JOIN wizard_steps ws ON ws.wizard_id = w.id
        """
        wizard_params: list[Any] = []
        if created_by:
            wizard_sql += " WHERE w.created_by = ?"
            wizard_params.append(created_by)
        wizard_sql += " GROUP BY COALESCE(w.rule_pack, 'wizard')"
        wizard_rows = conn.execute(wizard_sql, tuple(wizard_params)).fetchall()
        option_rows = conn.execute(
            """
            SELECT DISTINCT pack_name AS name
            FROM rule_pack_options
            ORDER BY pack_name
            """
        ).fetchall()

    merged: dict[str, dict[str, Any]] = {}

    for row in explicit_rows:
        merged[str(row["name"])] = {
            "id": f"pack-{row['name']}",
            "name": row["name"],
            "status": row["status"] or "draft",
            "project_id": row["project_id"],
            "rules": [],
            "rule_count": int(row["rule_count"] or 0),
            "created_at": row["created_at"],
        }

    for row in grouped_rule_rows:
        name = str(row["name"])
        existing = merged.get(name)
        if existing:
            existing["rule_count"] = max(existing["rule_count"], int(row["rule_count"] or 0))
            existing["status"] = "active" if existing["rule_count"] > 0 else existing["status"]
            if not existing.get("created_at"):
                existing["created_at"] = row["updated_at"]
        else:
            merged[name] = {
                "id": f"pack-{name}",
                "name": name,
                "status": "active",
                "project_id": None,
                "rules": [],
                "rule_count": int(row["rule_count"] or 0),
                "created_at": row["updated_at"],
            }

    for row in wizard_rows:
        name = str(row["name"] or "wizard")
        wizard_count = int(row["wizard_count"] or 0)
        if wizard_count <= 0:
            continue
        existing = merged.get(name)
        if existing:
            existing["rule_count"] = existing["rule_count"] + wizard_count
            existing["status"] = "active"
            if not existing.get("created_at"):
                existing["created_at"] = row["updated_at"]
        else:
            merged[name] = {
                "id": f"pack-{name}",
                "name": name,
                "status": "active",
                "project_id": None,
                "rules": [],
                "rule_count": wizard_count,
                "created_at": row["updated_at"],
            }

    for row in option_rows:
        name = str(row["name"])
        if name not in merged:
            merged[name] = {
                "id": f"pack-{name}",
                "name": name,
                "status": "available",
                "project_id": None,
                "rules": [],
                "rule_count": 0,
                "created_at": None,
            }

    result = list(merged.values())
    result.sort(key=lambda item: (item["rule_count"], item["name"]), reverse=True)
    return result


def get_rules_for_pack(
    pack_name: str,
    project_id: str | None = None,
    created_by: str | None = None,
) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        sql = """
            SELECT row_id, rule_id, yaml_text, confidence, category, severity, duplicate_of, similarity,
                   source_snippet, status, rule_pack, project_id
            FROM rules
            WHERE COALESCE(rule_pack, 'generic') = ?
              AND LOWER(status) IN ('saved', 'approved', 'edited')
        """
        params: list[Any] = [pack_name]
        if project_id:
            sql += " AND project_id = ?"
            params.append(project_id)
        if created_by:
            sql += " AND created_by = ?"
            params.append(created_by)
        sql += " ORDER BY row_id DESC"
        rows = conn.execute(sql, tuple(params)).fetchall()

    rules = [
        {
            "db_id": int(row["row_id"]),
            "yaml": row["yaml_text"],
            "confidence": row["confidence"],
            "category": row["category"],
            "_id": row["rule_id"],
            "_severity": row["severity"],
            "duplicate_of": row["duplicate_of"],
            "similarity": row["similarity"],
            "source_snippet": row["source_snippet"],
            "rule_pack": row["rule_pack"] or "generic",
            "project_id": row["project_id"],
            "status": "approved" if str(row["status"]).lower() in {"approved", "saved"} else row["status"],
        }
        for row in rows
    ]

    has_wizard_rule = any(str(r.get("category")).lower() == "wizard" for r in rules)
    if not has_wizard_rule:
        with _get_conn() as conn:
            wizard_sql = """
                SELECT id
                FROM wizards
                WHERE COALESCE(rule_pack, 'wizard') = ?
            """
            wizard_params: list[Any] = [pack_name]
            if created_by:
                wizard_sql += " AND created_by = ?"
                wizard_params.append(created_by)
            wizard_ids = [row["id"] for row in conn.execute(wizard_sql, tuple(wizard_params)).fetchall()]
            if not wizard_ids and created_by:
                wizard_ids = [
                    row["id"]
                    for row in conn.execute(
                        """
                        SELECT id
                        FROM wizards
                        WHERE COALESCE(rule_pack, 'wizard') = ?
                        """,
                        (pack_name,),
                    ).fetchall()
                ]

            if wizard_ids:
                placeholders = ",".join("?" for _ in wizard_ids)
                step_sql = f"""
                    SELECT wizard_id, step_no, rule_id, yaml_text, created_by, created_at
                    FROM wizard_steps
                    WHERE wizard_id IN ({placeholders})
                    ORDER BY wizard_id, step_no
                """
                step_rows = conn.execute(step_sql, tuple(wizard_ids)).fetchall()
                for row in step_rows:
                    try:
                        parsed = yaml.safe_load(row["yaml_text"])
                    except Exception:
                        parsed = {}
                    rules.append(
                        {
                            "db_id": None,
                            "yaml": row["yaml_text"],
                            "confidence": float(parsed.get("confidence", 0.7)) if isinstance(parsed, dict) else 0.7,
                            "category": "wizard",
                            "_id": parsed.get("id") if isinstance(parsed, dict) else row["rule_id"],
                            "_severity": parsed.get("severity") if isinstance(parsed, dict) else None,
                            "duplicate_of": None,
                            "similarity": None,
                            "source_snippet": None,
                            "rule_pack": pack_name,
                            "project_id": project_id,
                            "status": "approved",
                        }
                    )

    return rules


def delete_rule_pack(pack_name: str, created_by: str | None = None) -> int:
    """
    Delete a pack and all rules associated with it.
    Returns number of deleted rule rows.
    """
    with _get_conn() as conn:
        sql = "DELETE FROM rules WHERE COALESCE(rule_pack, 'generic') = ?"
        params: list[Any] = [pack_name]
        if created_by:
            sql += " AND created_by = ?"
            params.append(created_by)
        deleted_rules = conn.execute(sql, tuple(params)).rowcount

        wizard_sql = "SELECT id FROM wizards WHERE COALESCE(rule_pack, 'wizard') = ?"
        wizard_params: list[Any] = [pack_name]
        if created_by:
            wizard_sql += " AND created_by = ?"
            wizard_params.append(created_by)
        wizard_ids = [str(row["id"]) for row in conn.execute(wizard_sql, tuple(wizard_params)).fetchall()]
        if wizard_ids:
            placeholders = ",".join("?" for _ in wizard_ids)
            conn.execute(
                f"DELETE FROM wizard_steps WHERE wizard_id IN ({placeholders})",
                tuple(wizard_ids),
            )
            conn.execute(
                f"DELETE FROM wizards WHERE id IN ({placeholders})",
                tuple(wizard_ids),
            )
        conn.execute(
            "DELETE FROM packs WHERE name = ?",
            (pack_name,),
        )
        conn.execute(
            "DELETE FROM rule_pack_options WHERE pack_name = ?",
            (pack_name,),
        )
    return int(deleted_rules or 0)


def delete_rule_by_row_id(pack_name: str, row_id: int, created_by: str | None = None) -> bool:
    with _get_conn() as conn:
        sql = """
            DELETE FROM rules
            WHERE row_id = ? AND COALESCE(rule_pack, 'generic') = ?
        """
        params: list[Any] = [row_id, pack_name]
        if created_by:
            sql += " AND created_by = ?"
            params.append(created_by)
        cur = conn.execute(sql, tuple(params))
        return cur.rowcount > 0


def update_rule_yaml_by_row_id(
    pack_name: str,
    row_id: int,
    yaml_text: str,
    created_by: str | None = None,
) -> dict[str, Any] | None:
    text = str(yaml_text or "").strip()
    if not text:
        raise ValueError("yaml is required")
    try:
        parsed = yaml.safe_load(text)
    except Exception as exc:
        raise ValueError(f"invalid yaml: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("yaml must be a mapping")

    derived = _derive_rule_fields({"yaml": text})
    normalized_pack = str(pack_name or "generic").strip() or "generic"

    with _get_conn() as conn:
        sql = """
            SELECT row_id, raw_json
            FROM rules
            WHERE row_id = ? AND COALESCE(rule_pack, 'generic') = ?
        """
        params: list[Any] = [row_id, normalized_pack]
        if created_by:
            sql += " AND created_by = ?"
            params.append(created_by)
        row = conn.execute(sql, tuple(params)).fetchone()
        if not row:
            return None

        raw_json = str(row["raw_json"] or "")
        try:
            raw_obj = json.loads(raw_json) if raw_json else {}
        except Exception:
            raw_obj = {}
        if not isinstance(raw_obj, dict):
            raw_obj = {}
        raw_obj["yaml"] = text
        raw_obj["_id"] = derived["rule_id"]
        raw_obj["category"] = derived["category"]
        raw_obj["_severity"] = derived["severity"]
        raw_obj["confidence"] = derived["confidence"]

        conn.execute(
            """
            UPDATE rules
            SET rule_id = ?, yaml_text = ?, category = ?, severity = ?, confidence = ?,
                status = 'edited', raw_json = ?
            WHERE row_id = ?
            """,
            (
                derived["rule_id"],
                text,
                derived["category"],
                derived["severity"],
                derived["confidence"],
                json.dumps(raw_obj),
                row_id,
            ),
        )

    return {
        "db_id": int(row_id),
        "yaml": text,
        "confidence": float(derived["confidence"]),
        "category": str(derived["category"]),
        "_id": str(derived["rule_id"]),
        "_severity": str(derived["severity"]),
        "status": "edited",
        "rule_pack": normalized_pack,
    }


def delete_wizard(wizard_id: str, created_by: str | None = None) -> bool:
    if not wizard_id:
        return False
    with _get_conn() as conn:
        wizard_sql = "SELECT id FROM wizards WHERE id = ?"
        wizard_params: list[Any] = [wizard_id]
        if created_by:
            wizard_sql += " AND created_by = ?"
            wizard_params.append(created_by)
        wizard = conn.execute(wizard_sql, tuple(wizard_params)).fetchone()
        if not wizard:
            # Fallback: treat input as rule_id and resolve wizard_id from wizard_steps
            step_row = conn.execute(
                "SELECT wizard_id FROM wizard_steps WHERE rule_id = ?",
                (wizard_id,),
            ).fetchone()
            if not step_row:
                return False
            wizard_id = str(step_row["wizard_id"])
            wizard_params = [wizard_id]
            if created_by:
                wizard_sql = "SELECT id FROM wizards WHERE id = ? AND created_by = ?"
                wizard_params.append(created_by)
            wizard = conn.execute(wizard_sql, tuple(wizard_params)).fetchone()
            if not wizard:
                return False

        step_rows = conn.execute(
            "SELECT rule_id FROM wizard_steps WHERE wizard_id = ?",
            (wizard_id,),
        ).fetchall()
        rule_ids = [row["rule_id"] for row in step_rows]

        conn.execute("DELETE FROM wizard_steps WHERE wizard_id = ?", (wizard_id,))
        conn.execute("DELETE FROM wizards WHERE id = ?", (wizard_id,))

        if rule_ids:
            placeholders = ",".join("?" for _ in rule_ids)
            rule_sql = f"DELETE FROM rules WHERE rule_id IN ({placeholders})"
            rule_params: list[Any] = list(rule_ids)
            if created_by:
                rule_sql += " AND created_by = ?"
                rule_params.append(created_by)
            conn.execute(rule_sql, tuple(rule_params))
    return True


def get_rule_summary(created_by: str | None = None) -> dict[str, int]:
    categories = ["code", "design", "naming", "performance", "template", "wizard"]
    counts = {key: 0 for key in categories}
    naming_from_code = 0
    performance_from_code = 0
    with _get_conn() as conn:
        sql = """
            SELECT category, yaml_text
            FROM rules
            WHERE LOWER(status) IN ('saved', 'approved', 'edited')
              AND LOWER(category) <> 'wizard'
        """
        params: list[Any] = []
        if created_by:
            sql += " AND created_by = ?"
            params.append(created_by)
        rows = conn.execute(sql, tuple(params)).fetchall()

        wizard_sql = "SELECT COUNT(*) FROM wizards"
        wizard_params: list[Any] = []
        if created_by:
            wizard_sql += " WHERE created_by = ?"
            wizard_params.append(created_by)
        wizard_count = int(conn.execute(wizard_sql, tuple(wizard_params)).fetchone()[0])

    for row in rows:
        category = str(row["category"]).lower()
        if category in counts:
            counts[category] += 1
        if category != "code":
            continue
        try:
            parsed = yaml.safe_load(str(row["yaml_text"] or ""))
        except Exception:
            parsed = {}
        subtags = []
        if isinstance(parsed, dict):
            raw_subtags = parsed.get("subtags")
            if isinstance(raw_subtags, list):
                subtags = [
                    str(item or "").strip().lower()
                    for item in raw_subtags
                ]
        if "naming" in subtags:
            naming_from_code += 1
        if "performance" in subtags:
            performance_from_code += 1

    code_total = counts["code"] + counts["naming"] + counts["performance"]
    code_naming_total = naming_from_code + counts["naming"]
    code_performance_total = performance_from_code + counts["performance"]

    counts["wizard"] = wizard_count
    counts["code_total"] = code_total
    counts["code_naming"] = code_naming_total
    counts["code_performance"] = code_performance_total
    counts["total"] = code_total + counts["design"] + counts["template"] + counts["wizard"]
    return counts


def _template_backfill_terms(selector_pattern: str, snippet: str, title: str, description: str) -> list[str]:
    source = f"{selector_pattern}\n{title}\n{description}\n{snippet}".lower()
    words = re.findall(r"[a-z0-9_]{2,}", source)
    raw_terms: set[str] = set()
    for word in words:
        for part in word.split("_"):
            part = part.strip()
            if len(part) >= 2:
                raw_terms.add(part)

    term_map = {
        "emp": "employee",
        "employees": "employee",
        "employee": "employee",
        "mgr": "manager",
        "manager": "manager",
        "mss": "manager",
        "reportee": "reportee",
        "reportees": "reportee",
        "active": "active",
        "pernr": "personnel",
        "role": "role",
        "teamviewer": "team",
        "team": "team",
        "get": "retrieve",
        "fetch": "retrieve",
        "retrieve": "retrieve",
        "molga": "molga",
        "country": "country",
        "land1": "country",
    }
    skip_terms = {"abap", "type", "data", "iv", "ev", "lt", "gv", "zcl", "reuse"}
    normalized: list[str] = []
    for raw in raw_terms:
        mapped = term_map.get(raw, raw)
        if mapped in skip_terms or len(mapped) < 3:
            continue
        normalized.append(mapped)

    ordered: list[str] = []
    for item in ["employee", "manager", "reportee", "country", "molga", "retrieve", "personnel", "active", "role", "team"]:
        if item in normalized and item not in ordered:
            ordered.append(item)
    for item in sorted(set(normalized)):
        if item not in ordered:
            ordered.append(item)
    return ordered[:12]


def _template_backfill_scope(text: str) -> str:
    lowered = (text or "").lower()
    if any(term in lowered for term in ("manager", "reportee", "teamviewer", "mss")):
        return "manager"
    if any(term in lowered for term in ("org", "organization", "team")):
        return "org"
    return "self"


def _template_backfill_intent(text: str) -> str:
    lowered = (text or "").lower()
    if any(term in lowered for term in ("country", "molga", "land1", "nationality")):
        return "get_country"
    if any(term in lowered for term in ("manager", "reportee", "teamviewer", "mss")):
        return "get_manager_team"
    if any(term in lowered for term in ("employee", "pernr", "personnel")):
        return "get_employee"
    return "generic_template"


def backfill_template_metadata(created_by: str | None = None, limit: int = 5000) -> dict[str, int]:
    scanned = 0
    updated = 0
    skipped = 0
    failed = 0

    with _get_conn() as conn:
        sql = """
            SELECT row_id, yaml_text, raw_json
            FROM rules
            WHERE LOWER(COALESCE(category, '')) = 'template'
        """
        params: list[Any] = []
        if created_by:
            sql += " AND created_by = ?"
            params.append(created_by)
        sql += " ORDER BY row_id DESC LIMIT ?"
        params.append(max(1, min(int(limit or 5000), 20000)))
        rows = conn.execute(sql, tuple(params)).fetchall()

        for row in rows:
            scanned += 1
            row_id = int(row["row_id"])
            yaml_text = str(row["yaml_text"] or "")
            try:
                parsed = yaml.safe_load(yaml_text)
            except Exception:
                failed += 1
                continue
            if not isinstance(parsed, dict):
                failed += 1
                continue
            if str(parsed.get("type") or "").strip().lower() != "template":
                skipped += 1
                continue

            metadata = parsed.get("metadata")
            if isinstance(metadata, dict) and metadata.get("intent") and metadata.get("scope"):
                skipped += 1
                continue

            selector_pattern = ""
            selector = parsed.get("selector")
            if isinstance(selector, dict):
                selector_pattern = str(selector.get("pattern") or "").strip()
            elif isinstance(selector, str):
                selector_pattern = selector.strip()
            title = str(parsed.get("title") or "").strip()
            description = str(parsed.get("description") or "").strip()
            snippet = ""
            template_block = parsed.get("template")
            if isinstance(template_block, dict):
                snippet = str(template_block.get("snippet") or "").strip()

            keywords = _template_backfill_terms(selector_pattern, snippet, title, description)
            combined_text = "\n".join([title, description, selector_pattern, snippet]).lower()
            parsed["metadata"] = {
                "intent": _template_backfill_intent(combined_text),
                "scope": _template_backfill_scope(combined_text),
                "entities": [e for e in ("employee", "manager", "reportee") if e in combined_text],
                "domain_fields": [d for d in ("molga", "country", "land1", "pernr", "personnel") if d in combined_text],
                "keywords": keywords,
                "source_type": "template",
                "confidence": float(parsed.get("confidence", 0.9) or 0.9),
            }

            updated_yaml = yaml.safe_dump(parsed, sort_keys=False, width=120)
            updated_raw_json = str(row["raw_json"] or "")
            try:
                raw_obj = json.loads(updated_raw_json) if updated_raw_json else {}
            except Exception:
                raw_obj = {}
            if isinstance(raw_obj, dict):
                raw_obj["yaml"] = updated_yaml
                updated_raw_json = json.dumps(raw_obj)
            else:
                updated_raw_json = json.dumps({"yaml": updated_yaml})

            conn.execute(
                """
                UPDATE rules
                SET yaml_text = ?, raw_json = ?
                WHERE row_id = ?
                """,
                (updated_yaml, updated_raw_json, row_id),
            )
            updated += 1

    return {
        "scanned": scanned,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
    }


def get_rule_pack_options(rule_type: str | None = None) -> list[str]:
    with _get_conn() as conn:
        if rule_type:
            rows = conn.execute(
                """
                SELECT pack_name
                FROM rule_pack_options
                WHERE rule_type = ?
                ORDER BY pack_name
                """,
                (rule_type.lower(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT pack_name FROM rule_pack_options ORDER BY pack_name"
            ).fetchall()
    return [str(row["pack_name"]) for row in rows]


def get_ui_config() -> dict[str, str]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT config_key, config_value FROM ui_config").fetchall()
    data = {str(row["config_key"]): str(row["config_value"]) for row in rows}
    return {
        "app_footer": data.get("app_footer", "Zalaris Code Governance"),
        "platform_title": data.get("platform_title", "Zalaris Code Governance Platform"),
        "default_user": data.get("default_user", "name@zalaris.com"),
    }


def _deep_merge_dict(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _looks_masked_secret(value: str) -> bool:
    text = str(value or "").strip()
    return bool(text) and set(text) <= {"*"}


def _mask_secret(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}{'*' * (len(text) - 8)}{text[-4:]}"


def _load_app_settings_unmasked() -> dict[str, Any]:
    defaults = copy.deepcopy(DEFAULT_APP_SETTINGS)
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT config_value FROM ui_config WHERE config_key = ?",
            (APP_SETTINGS_KEY,),
        ).fetchone()
    if not row:
        return defaults
    try:
        loaded = json.loads(str(row["config_value"]))
    except Exception:
        loaded = {}
    if not isinstance(loaded, dict):
        loaded = {}
    return _deep_merge_dict(defaults, loaded)


def _sanitize_app_settings(settings: dict[str, Any]) -> dict[str, Any]:
    sanitized = copy.deepcopy(settings)
    ai = sanitized.get("ai_assistant_controls")
    if isinstance(ai, dict):
        key = str(ai.get("model_api_key") or "").strip()
        ai["has_model_api_key"] = bool(key)
        ai["model_api_key_masked"] = _mask_secret(key) if key else ""
        ai.pop("model_api_key", None)
    return sanitized


def get_app_settings_unmasked() -> dict[str, Any]:
    return _load_app_settings_unmasked()


def get_model_api_key() -> str:
    settings = get_app_settings_unmasked()
    ai = settings.get("ai_assistant_controls")
    if isinstance(ai, dict):
        key = str(ai.get("model_api_key") or "").strip()
        if key:
            return key
    return str(os.getenv("OPENAI_API_KEY") or "").strip()


def get_ai_model_name(default: str = "gpt-4o-mini") -> str:
    settings = get_app_settings_unmasked()
    ai = settings.get("ai_assistant_controls")
    if isinstance(ai, dict):
        model = str(ai.get("model") or "").strip()
        if model:
            return model
    return default


def get_app_settings() -> dict[str, Any]:
    return _sanitize_app_settings(_load_app_settings_unmasked())


def update_app_settings(updates: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(updates, dict):
        return get_app_settings()
    current = get_app_settings_unmasked()
    sanitized_updates = copy.deepcopy(updates)
    ai_updates = sanitized_updates.get("ai_assistant_controls")
    if isinstance(ai_updates, dict):
        raw_key = ai_updates.get("model_api_key")
        if isinstance(raw_key, str):
            trimmed_key = raw_key.strip()
            if not trimmed_key:
                ai_updates["model_api_key"] = ""
            elif _looks_masked_secret(trimmed_key):
                ai_updates.pop("model_api_key", None)
            else:
                ai_updates["model_api_key"] = trimmed_key
    merged = _deep_merge_dict(current, sanitized_updates)
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO ui_config (config_key, config_value)
            VALUES (?, ?)
            ON CONFLICT(config_key) DO UPDATE SET config_value = excluded.config_value
            """,
            (APP_SETTINGS_KEY, json.dumps(merged, ensure_ascii=True)),
        )
    return _sanitize_app_settings(merged)


def update_ui_config(updates: dict[str, str]) -> dict[str, str]:
    allowed = {"app_footer", "platform_title", "default_user"}
    with _get_conn() as conn:
        for key, value in updates.items():
            if key not in allowed:
                continue
            conn.execute(
                """
                INSERT INTO ui_config (config_key, config_value)
                VALUES (?, ?)
                ON CONFLICT(config_key) DO UPDATE SET config_value = excluded.config_value
                """,
                (key, str(value)),
            )
    return get_ui_config()


def list_rule_pack_option_rows(rule_type: str | None = None) -> list[dict[str, str]]:
    with _get_conn() as conn:
        if rule_type:
            rows = conn.execute(
                """
                SELECT id, rule_type, pack_name
                FROM rule_pack_options
                WHERE rule_type = ?
                ORDER BY rule_type, pack_name
                """,
                (rule_type.lower(),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, rule_type, pack_name
                FROM rule_pack_options
                ORDER BY rule_type, pack_name
                """
            ).fetchall()
    return [
        {"id": str(row["id"]), "rule_type": str(row["rule_type"]), "pack_name": str(row["pack_name"])}
        for row in rows
    ]


def create_rule_pack_option(rule_type: str, pack_name: str) -> dict[str, str]:
    row = {
        "id": f"rpo-{uuid.uuid4().hex[:10]}",
        "rule_type": rule_type.lower().strip(),
        "pack_name": pack_name.strip(),
    }
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO rule_pack_options (id, rule_type, pack_name) VALUES (?, ?, ?)",
            (row["id"], row["rule_type"], row["pack_name"]),
        )
    return row


def delete_rule_pack_option(option_id: str) -> bool:
    with _get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM rule_pack_options WHERE id = ?",
            (option_id,),
        )
        return cur.rowcount > 0


def list_dashboard_violations(limit: int = 50, developer: str | None = None) -> list[dict[str, str]]:
    with _get_conn() as conn:
        sql = """
            SELECT id, rule_pack, object_name, transport, developer, severity, status, created_at
            FROM dashboard_violations
        """
        params: list[Any] = []
        if developer:
            sql += " WHERE developer = ?"
            params.append(developer)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [
        {
            "id": str(row["id"]),
            "rule_pack": str(row["rule_pack"]),
            "object_name": str(row["object_name"]),
            "transport": str(row["transport"]),
            "developer": str(row["developer"]),
            "severity": str(row["severity"]),
            "status": str(row["status"] or "Not Fixed"),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


def create_dashboard_violation(
    rule_pack: str,
    object_name: str,
    transport: str,
    developer: str,
    severity: str,
    status: str = "Not Fixed",
) -> dict[str, str]:
    normalized_status = "Fixed" if str(status or "").strip().lower() == "fixed" else "Not Fixed"
    row = {
        "id": f"vio-{uuid.uuid4().hex[:12]}",
        "rule_pack": rule_pack.strip(),
        "object_name": object_name.strip(),
        "transport": transport.strip(),
        "developer": developer.strip(),
        "severity": severity.upper().strip(),
        "status": normalized_status,
        "created_at": _now_iso(),
    }
    with _get_conn() as conn:
        if normalized_status == "Fixed":
            updated = conn.execute(
                """
                UPDATE dashboard_violations
                SET status = 'Fixed', created_at = ?
                WHERE object_name = ? AND developer = ? AND LOWER(status) <> 'fixed'
                """,
                (row["created_at"], row["object_name"], row["developer"]),
            ).rowcount
            return {
                "id": row["id"],
                "rule_pack": row["rule_pack"],
                "object_name": row["object_name"],
                "transport": row["transport"],
                "developer": row["developer"],
                "severity": row["severity"],
                "status": "Fixed",
                "created_at": row["created_at"],
                "updated": str(int(updated or 0)),
            }

        existing = conn.execute(
            """
            SELECT id
            FROM dashboard_violations
            WHERE object_name = ? AND developer = ? AND LOWER(status) = 'not fixed'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (row["object_name"], row["developer"]),
        ).fetchone()
        if existing:
            row["id"] = str(existing["id"])
            conn.execute(
                """
                UPDATE dashboard_violations
                SET rule_pack = ?, transport = ?, severity = ?, status = 'Not Fixed', created_at = ?
                WHERE id = ?
                """,
                (
                    row["rule_pack"],
                    row["transport"],
                    row["severity"],
                    row["created_at"],
                    row["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO dashboard_violations (
                    id, rule_pack, object_name, transport, developer, severity, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["rule_pack"],
                    row["object_name"],
                    row["transport"],
                    row["developer"],
                    row["severity"],
                    row["status"],
                    row["created_at"],
                ),
            )
    return row


def delete_dashboard_violation(violation_id: str) -> bool:
    with _get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM dashboard_violations WHERE id = ?",
            (violation_id,),
        )
        return cur.rowcount > 0


def clear_dashboard_violations_by_date_range(start_date: str, end_date: str) -> int:
    start_bound, end_bound = _resolve_date_bounds(start_date, end_date)
    if not start_bound or not end_bound:
        raise ValueError("start_date and end_date must be valid ISO dates (YYYY-MM-DD)")
    with _get_conn() as conn:
        cur = conn.execute(
            """
            DELETE FROM dashboard_violations
            WHERE date(created_at) >= date(?)
              AND date(created_at) <= date(?)
            """,
            (start_bound, end_bound),
        )
        return int(cur.rowcount or 0)


def get_dashboard_overview(created_by: str | None = None) -> dict[str, Any]:
    with _get_conn() as conn:
        if created_by:
            total_rules = int(
                conn.execute(
                    "SELECT COUNT(*) FROM rules WHERE created_by = ?",
                    (created_by,),
                ).fetchone()[0]
            )
            saved_rules = int(
                conn.execute(
                    "SELECT COUNT(*) FROM rules WHERE LOWER(status) IN ('approved','saved') AND created_by = ?",
                    (created_by,),
                ).fetchone()[0]
            )
        else:
            total_rules = int(conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0])
            saved_rules = int(
                conn.execute(
                    "SELECT COUNT(*) FROM rules WHERE LOWER(status) IN ('approved','saved')"
                ).fetchone()[0]
            )
        projects = int(conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0])

        today = datetime.now(timezone.utc).date().isoformat()
        if created_by:
            violations_today = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM dashboard_violations
                    WHERE created_at LIKE ?
                      AND developer = ?
                      AND LOWER(COALESCE(status, 'not fixed')) = 'not fixed'
                    """,
                    (f"{today}%", created_by),
                ).fetchone()[0]
            )
            trend_rows = conn.execute(
                """
                SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS count
                FROM dashboard_violations
                WHERE date(created_at) >= date('now', '-6 day')
                  AND developer = ?
                  AND LOWER(COALESCE(status, 'not fixed')) = 'not fixed'
                GROUP BY day
                ORDER BY day
                """,
                (created_by,),
            ).fetchall()
            violation_rows = conn.execute(
                """
                SELECT rule_pack, object_name, transport, developer, severity, status
                FROM dashboard_violations
                WHERE developer = ?
                ORDER BY created_at DESC
                LIMIT 15
                """,
                (created_by,),
            ).fetchall()
        else:
            violations_today = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM dashboard_violations
                    WHERE created_at LIKE ?
                      AND LOWER(COALESCE(status, 'not fixed')) = 'not fixed'
                    """,
                    (f"{today}%",),
                ).fetchone()[0]
            )
            trend_rows = conn.execute(
                """
                SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS count
                FROM dashboard_violations
                WHERE date(created_at) >= date('now', '-6 day')
                  AND LOWER(COALESCE(status, 'not fixed')) = 'not fixed'
                GROUP BY day
                ORDER BY day
                """
            ).fetchall()
            violation_rows = conn.execute(
                """
                SELECT rule_pack, object_name, transport, developer, severity, status
                FROM dashboard_violations
                ORDER BY created_at DESC
                LIMIT 15
                """
            ).fetchall()

    by_day = {str(row["day"]): int(row["count"]) for row in trend_rows}
    trend_data: list[dict[str, Any]] = []
    now_day = datetime.now(timezone.utc).date()
    for i in range(6, -1, -1):
        day = now_day - timedelta(days=i)
        trend_data.append(
            {
                "date": day.strftime("%a"),
                "violations": by_day.get(day.isoformat(), 0),
            }
        )

    compliance_score = round((saved_rules / total_rules) * 100, 1) if total_rules else 0.0
    kpis = [
        {"title": "Total Rules", "value": total_rules, "color": "text-indigo-700"},
        {"title": "Violations Today", "value": violations_today, "color": "text-red-600"},
        {"title": "Compliance Score", "value": f"{compliance_score}%", "color": "text-green-600"},
        {"title": "Projects", "value": projects, "color": "text-sky-700"},
    ]

    violations = [
        {
            "rulePack": row["rule_pack"],
            "object": row["object_name"],
            "transport": row["transport"],
            "developer": row["developer"],
            "severity": row["severity"].capitalize(),
            "status": str(row["status"] or "Not Fixed"),
        }
        for row in violation_rows
    ]

    return {
        "kpis": kpis,
        "trendData": trend_data,
        "violations": violations,
    }


def compute_analytics_overview(
    created_by: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    start_bound, end_bound = _resolve_date_bounds(start_date, end_date)
    with _get_conn() as conn:
        sql = """
            SELECT project_id, rule_id, category, severity, status, created_at
            FROM rules
        """
        where_clauses: list[str] = []
        params: list[Any] = []
        if created_by:
            where_clauses.append("created_by = ?")
            params.append(created_by)
        if start_bound:
            where_clauses.append("date(created_at) >= date(?)")
            params.append(start_bound)
        if end_bound:
            where_clauses.append("date(created_at) <= date(?)")
            params.append(end_bound)
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        rows = conn.execute(sql, tuple(params)).fetchall()
        projects = conn.execute("SELECT id, name FROM projects").fetchall()

    entries = [dict(row) for row in rows]
    # Templates and wizards are guidance assets, not violation analytics entities.
    entries = [
        entry
        for entry in entries
        if str(entry.get("category", "")).lower() not in {"template", "wizard"}
    ]
    project_name_by_id = {row["id"]: row["name"] for row in projects}

    if start_bound and end_bound:
        start_dt = datetime.fromisoformat(start_bound).date()
        end_dt = datetime.fromisoformat(end_bound).date()
    else:
        end_dt = datetime.now(timezone.utc).date()
        start_dt = end_dt - timedelta(days=6)
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    span_days = (end_dt - start_dt).days + 1
    if span_days > 366:
        start_dt = end_dt - timedelta(days=365)

    buckets: list[dict[str, Any]] = []
    day_cursor = start_dt
    while day_cursor <= end_dt:
        day_entries = [
            entry
            for entry in entries
            if str(entry.get("created_at", "")).startswith(day_cursor.isoformat())
        ]
        evaluated = len(day_entries)
        approved = len(
            [
                e
                for e in day_entries
                if str(e.get("status", "")).lower() in {"approved", "saved"}
            ]
        )
        score = round((approved / evaluated) * 100, 1) if evaluated else 0.0
        buckets.append(
            {
                "date": day_cursor.isoformat(),
                "label": day_cursor.strftime("%d %b"),
                "score": score,
                "evaluated": evaluated,
                "approved": approved,
            }
        )
        day_cursor += timedelta(days=1)

    heatmap_counts: dict[tuple[str, str], int] = {}
    for entry in entries:
        key = (
            str(entry.get("category", "code")).lower(),
            str(entry.get("severity", "MAJOR")).upper(),
        )
        heatmap_counts[key] = heatmap_counts.get(key, 0) + 1
    violation_heatmap = [
        {"category": category, "severity": severity, "count": count}
        for (category, severity), count in heatmap_counts.items()
    ]

    lifecycle = {
        "extracted": len(
            [e for e in entries if str(e.get("status", "")).lower() == "extracted"]
        ),
        "edited": len(
            [e for e in entries if str(e.get("status", "")).lower() == "edited"]
        ),
        "approved": len(
            [
                e
                for e in entries
                if str(e.get("status", "")).lower() in {"approved", "saved"}
            ]
        ),
        "saved": len(
            [e for e in entries if str(e.get("status", "")).lower() == "saved"]
        ),
    }
    lifecycle_funnel = [{"stage": stage, "count": count} for stage, count in lifecycle.items()]

    top_map: dict[str, dict[str, Any]] = {}
    for entry in entries:
        rid = str(entry.get("rule_id") or "unknown.rule")
        if rid not in top_map:
            top_map[rid] = {"rule_id": rid, "count": 0, "projects": set()}
        top_map[rid]["count"] += 1
        top_map[rid]["projects"].add(
            project_name_by_id.get(str(entry.get("project_id")), "Unknown Project")
        )

    top_violations = sorted(top_map.values(), key=lambda item: item["count"], reverse=True)[:5]
    for item in top_violations:
        item["projects"] = sorted(item["projects"])

    total_rules = len(entries)
    total_saved = lifecycle["saved"]
    overall_compliance = round((total_saved / total_rules) * 100, 1) if total_rules else 0.0

    return {
        "summary": {
            "total_rules": total_rules,
            "saved_rules": total_saved,
            "overall_compliance": overall_compliance,
        },
        "compliance_trend": buckets,
        "violation_heatmap": violation_heatmap,
        "lifecycle_funnel": lifecycle_funnel,
        "top_violations": top_violations,
    }


def compute_developer_analytics(
    created_by: str | None = None,
    developer: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    start_bound, end_bound = _resolve_date_bounds(start_date, end_date)
    with _get_conn() as conn:
        sql = """
            SELECT developer, severity, created_at
            FROM dashboard_violations
        """
        where_clauses: list[str] = []
        params: list[Any] = []
        where_clauses.append("LOWER(COALESCE(status, 'not fixed')) = 'not fixed'")
        if created_by:
            where_clauses.append("developer = ?")
            params.append(created_by)
        if developer:
            where_clauses.append("developer = ?")
            params.append(developer)
        if start_bound:
            where_clauses.append("date(created_at) >= date(?)")
            params.append(start_bound)
        if end_bound:
            where_clauses.append("date(created_at) <= date(?)")
            params.append(end_bound)
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        rows = conn.execute(sql, tuple(params)).fetchall()

    entries = [dict(row) for row in rows]
    if not entries:
        return {
            "summary": {
                "total_violations": 0,
                "active_developers": 0,
                "improving_developers": 0,
            },
            "by_developer": [],
            "improvement": [],
            "daily_by_developer": [],
        }

    if start_bound and end_bound:
        start_dt = datetime.fromisoformat(start_bound).date()
        end_dt = datetime.fromisoformat(end_bound).date()
    else:
        end_dt = datetime.now(timezone.utc).date()
        start_dt = end_dt - timedelta(days=13)
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    if (end_dt - start_dt).days > 120:
        start_dt = end_dt - timedelta(days=120)
    days = []
    day_cursor = start_dt
    while day_cursor <= end_dt:
        days.append(day_cursor)
        day_cursor += timedelta(days=1)
    day_keys = [d.isoformat() for d in days]

    developer_totals: dict[str, dict[str, Any]] = {}
    for entry in entries:
        developer = str(entry.get("developer") or "Unknown")
        severity = str(entry.get("severity") or "WARNING").upper()
        created_at = str(entry.get("created_at") or "")
        day = created_at[:10]

        if developer not in developer_totals:
            developer_totals[developer] = {
                "developer": developer,
                "total": 0,
                "ERROR": 0,
                "WARNING": 0,
                "INFO": 0,
                "other": 0,
                "by_day": {k: 0 for k in day_keys},
            }

        dev = developer_totals[developer]
        dev["total"] += 1
        if severity in {"ERROR", "WARNING", "INFO"}:
            dev[severity] += 1
        else:
            dev["other"] += 1

        if day in dev["by_day"]:
            dev["by_day"][day] += 1

    by_developer = sorted(
        [
            {
                "developer": item["developer"],
                "total": item["total"],
                "error": item["ERROR"],
                "warning": item["WARNING"],
                "info": item["INFO"],
                "other": item["other"],
            }
            for item in developer_totals.values()
        ],
        key=lambda x: x["total"],
        reverse=True,
    )

    improvement: list[dict[str, Any]] = []
    improving_developers = 0
    split_index = max(1, len(day_keys) // 2)
    prev_days = day_keys[:split_index]
    curr_days = day_keys[split_index:]
    for developer, data in developer_totals.items():
        prev_count = sum(int(data["by_day"][k]) for k in prev_days)
        curr_count = sum(int(data["by_day"][k]) for k in curr_days)
        delta = curr_count - prev_count
        improvement_pct = round(((prev_count - curr_count) / prev_count) * 100, 1) if prev_count > 0 else 0.0
        trend = "stable"
        if curr_count < prev_count:
            trend = "improving"
            improving_developers += 1
        elif curr_count > prev_count:
            trend = "declining"

        improvement.append(
            {
                "developer": developer,
                "previous_7d": prev_count,
                "current_7d": curr_count,
                "delta": delta,
                "improvement_pct": improvement_pct,
                "trend": trend,
            }
        )

    improvement.sort(key=lambda x: x["delta"])

    top_developers = [item["developer"] for item in by_developer[:3]]
    daily_by_developer: list[dict[str, Any]] = []
    for day in days:
        point: dict[str, Any] = {"date": day.strftime("%d %b")}
        for developer in top_developers:
            point[developer] = int(developer_totals[developer]["by_day"][day.isoformat()])
        daily_by_developer.append(point)

    return {
        "summary": {
            "total_violations": len(entries),
            "active_developers": len(developer_totals),
            "improving_developers": improving_developers,
        },
        "by_developer": by_developer,
        "improvement": improvement,
        "daily_by_developer": daily_by_developer,
    }


def list_analytics_developers(
    created_by: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[str]:
    start_bound, end_bound = _resolve_date_bounds(start_date, end_date)
    with _get_conn() as conn:
        sql = "SELECT DISTINCT developer FROM dashboard_violations"
        where_clauses: list[str] = []
        params: list[Any] = []
        where_clauses.append("LOWER(COALESCE(status, 'not fixed')) = 'not fixed'")
        if created_by:
            where_clauses.append("developer = ?")
            params.append(created_by)
        if start_bound:
            where_clauses.append("date(created_at) >= date(?)")
            params.append(start_bound)
        if end_bound:
            where_clauses.append("date(created_at) <= date(?)")
            params.append(end_bound)
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY developer"
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [str(row["developer"]) for row in rows if str(row["developer"]).strip()]


def seed_demo_projects() -> None:
    if not list_projects():
        create_project(
            name="MFP Development",
            description="Peoplehub application development.",
            members=[
                {"name": "Default User", "email": "name@zalaris.com", "role": "developer"},
            ],
        )
        create_project(
            name="ABAP Programming",
            description="ABAP HR Programming.",
            members=[
                {"name": "Senior Dev", "email": "senior.dev@example.com", "role": "senior_developer"},
            ],
        )
        create_project(
            name="S/4HANA Migration",
            description="Migration of code to S/4 HANA.",
            members=[
                {"name": "Developer", "email": "developer@example.com", "role": "developer"},
            ],
        )

    with _get_conn() as conn:
        existing_options = int(conn.execute("SELECT COUNT(*) FROM rule_pack_options").fetchone()[0])
        if existing_options == 0:
            seed_options = {
                "code": [
                    "abap-core-safety",
                    "abap-core-exception",
                    "abap-db-standards",
                    "abap-unit-tests",
                    "abap-core-syntax",
                ],
                "design": ["architecture-guidelines", "design-patterns"],
                "naming": ["naming-standards", "package-prefixes"],
                "performance": [
                    "performance-optimizations",
                    "sql-guidelines",
                    "abap-core-performance",
                ],
                "template": ["code-templates", "developer-snippets"],
                "wizard": ["multi-object-guided-dev", "rap-app-wizard"],
            }
            for rule_type, options in seed_options.items():
                for option in options:
                    conn.execute(
                        "INSERT INTO rule_pack_options (id, rule_type, pack_name) VALUES (?, ?, ?)",
                        (f"rpo-{uuid.uuid4().hex[:10]}", rule_type, option),
                    )

        existing_ui = int(conn.execute("SELECT COUNT(*) FROM ui_config").fetchone()[0])
        if existing_ui == 0:
            conn.executemany(
                "INSERT INTO ui_config (config_key, config_value) VALUES (?, ?)",
                [
                    ("app_footer", "Zalaris Code Governance"),
                    ("platform_title", "Zalaris Code Governance Platform"),
                    ("default_user", "name@zalaris.com"),
                ],
            )

        existing_violations = int(conn.execute("SELECT COUNT(*) FROM dashboard_violations").fetchone()[0])
        if existing_violations == 0:
            for violation in [
                {
                    "rule_pack": "abap-core-safety",
                    "object_name": "ZRP_MFP_CLOCK_UPDATE_DB",
                    "transport": "ZEDK1234456",
                    "developer": "Prashanth Selvam",
                    "severity": "ERROR",
                },
                {
                    "rule_pack": "abap-naming-conv",
                    "object_name": "ZCL_MFP_LEAVE_REQUEST",
                    "transport": "ZEDK1235656",
                    "developer": "Keerthivasan Vasudevan",
                    "severity": "WARNING",
                },
                {
                    "rule_pack": "security-base",
                    "object_name": "ZMFP_NETWORKS_WBS",
                    "transport": "ZEDK1237786",
                    "developer": "Duraimurugan Kathirvel",
                    "severity": "ERROR",
                },
            ]:
                conn.execute(
                    """
                    INSERT INTO dashboard_violations (
                        id, rule_pack, object_name, transport, developer, severity, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"vio-{uuid.uuid4().hex[:12]}",
                        violation["rule_pack"],
                        violation["object_name"],
                        violation["transport"],
                        violation["developer"],
                        violation["severity"],
                        _now_iso(),
                    ),
                )
