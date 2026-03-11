"""Unit tests for alert_rules and alert_events SQL column names.

Verifies that all queries use 'rule_id' / 'event_id' as the primary-key
column names (matching the DB schema) instead of the incorrect 'id'.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re


def _load_alerts_source() -> str:
    """Read the raw source of alerts.py — works on host, CI, and in Docker."""
    # 1. importlib — works when the package is pip-installed (e.g. in CI)
    try:
        spec = importlib.util.find_spec("document_service.presentation.routes.alerts")
        if spec and spec.origin:
            return pathlib.Path(spec.origin).read_text()
    except (ModuleNotFoundError, ValueError):
        pass

    # 2. Filesystem fallback candidates
    _here = pathlib.Path(__file__).resolve()
    candidates = [
        # Docker: mounted at /app
        pathlib.Path("/app/src/document_service/presentation/routes/alerts.py"),
        # Relative: __file__ parents[2] = services/document-service
        _here.parents[2] / "src" / "document_service" / "presentation" / "routes" / "alerts.py",
        # site-packages — any Python version under /usr/local/lib
        *[
            p / "document_service" / "presentation" / "routes" / "alerts.py"
            for p in pathlib.Path("/usr/local/lib").glob("python3.*/site-packages")
        ],
    ]
    for p in candidates:
        if p.exists():
            return p.read_text()
    raise FileNotFoundError(f"alerts.py not found. Tried: {candidates}")


def _load_db_updater_source() -> str:
    """Read the raw source of db_updater.py — works on host, CI, and in Docker."""
    # 1. importlib — works when the package is pip-installed (e.g. in CI)
    try:
        spec = importlib.util.find_spec("processing_service.infrastructure.db_updater")
        if spec and spec.origin:
            return pathlib.Path(spec.origin).read_text()
    except (ModuleNotFoundError, ValueError):
        pass

    # 2. Filesystem fallback candidates
    _here = pathlib.Path(__file__).resolve()
    candidates = [
        # Docker
        pathlib.Path("/processing-service/src/processing_service/infrastructure/db_updater.py"),
        # Relative: __file__ parents[3] = services/, then into processing-service
        _here.parents[3] / "processing-service" / "src" / "processing_service" / "infrastructure" / "db_updater.py",
        # site-packages — any Python version
        *[
            p / "processing_service" / "infrastructure" / "db_updater.py"
            for p in pathlib.Path("/usr/local/lib").glob("python3.*/site-packages")
        ],
    ]
    for p in candidates:
        if p.exists():
            return p.read_text()
    raise FileNotFoundError(f"db_updater.py not found. Tried: {[str(p) for p in candidates]}")

# ── alerts.py column names ────────────────────────────────────────────────────

class TestAlertsRouteColumnNames:
    def test_create_rule_returning_uses_rule_id(self):
        src = _load_alerts_source()
        assert re.search(r"RETURNING\s+rule_id", src), \
               "CREATE alert_rule RETURNING must use 'rule_id', not 'id'"

    def test_list_rules_select_uses_rule_id(self):
        src = _load_alerts_source()
        assert re.search(r"SELECT\s+rule_id", src), \
               "list_rules SELECT must include 'rule_id'"

    def test_delete_rule_where_uses_rule_id(self):
        src = _load_alerts_source()
        assert "rule_id = $1" in src, \
               "delete_rule WHERE must use 'rule_id = $1'"

    def test_toggle_rule_uses_rule_id(self):
        src = _load_alerts_source()
        assert src.count("rule_id") >= 4, \
               "Expected at least 4 occurrences of 'rule_id' in alerts.py"

    def test_list_events_select_uses_event_id(self):
        src = _load_alerts_source()
        assert "event_id" in src, \
               "list_events SELECT must include 'event_id'"

    def test_acknowledge_event_where_uses_event_id(self):
        src = _load_alerts_source()
        assert "event_id = $1" in src, \
               "acknowledge_event WHERE must use 'event_id = $1'"

    def test_map_rule_uses_rule_id_key(self):
        src = _load_alerts_source()
        assert 'row["rule_id"]' in src, \
               '_map_rule must read row["rule_id"], not row["id"]'

    def test_map_event_uses_event_id_key(self):
        src = _load_alerts_source()
        assert 'row["event_id"]' in src, \
               '_map_event must read row["event_id"], not row["id"]'

    def test_no_bare_id_in_returning_for_alert_rules(self):
        """Make sure 'RETURNING id' doesn't appear for alert_rules queries."""
        src = _load_alerts_source()
        bad_matches = re.findall(r"RETURNING\s+id[,\s\n]", src)
        assert not bad_matches, \
               f"Found 'RETURNING id' (should be 'rule_id'): {bad_matches}"


# ── db_updater.py column names ────────────────────────────────────────────────

class TestDbUpdaterColumnNames:
    def test_evaluate_alerts_selects_rule_id(self):
        src = _load_db_updater_source()
        assert re.search(r"SELECT\s+rule_id", src), \
               "evaluate_alerts must SELECT rule_id from alert_rules, not id"

    def test_insert_alert_event_uses_rule_id_key(self):
        src = _load_db_updater_source()
        assert 'rule["rule_id"]' in src, \
               'INSERT alert_event must use rule["rule_id"], not rule["id"]'

    def test_no_rule_id_access_as_plain_id(self):
        src = _load_db_updater_source()
        bad = re.findall(r'rule\["id"\]', src)
        assert not bad, \
               f"db_updater uses rule[\"id\"] — should be rule[\"rule_id\"]: {bad}"
