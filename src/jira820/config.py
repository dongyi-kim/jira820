"""Configuration: JIRA820_* environment variables merged over an optional YAML file.

Precedence: environment variable > YAML value > built-in default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

try:
    import yaml
except Exception:  # pragma: no cover - yaml is a hard dependency, guard for import order
    yaml = None


def _pick(env_key: str, yaml_val: Any, default: Any) -> Any:
    """env var wins -> else YAML value -> else default."""
    v = os.getenv(env_key)
    if v is not None and v != "":
        return v
    if yaml_val is not None:
        return yaml_val
    return default


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ── default dataset (generic, business-neutral) ──
DEFAULT_MODULES = ["Web", "API", "Mobile", "Payments", "Platform", "Infra"]
DEFAULT_COMPONENTS_EXTRA = ["Support"]  # non-module components (e.g. a customer-facing bucket)

# statusName, internal category (todo|inprogress|done), numeric id
DEFAULT_STATUSES = [
    ("Open", "todo", "1"),
    ("In Progress", "inprogress", "3"),
    ("In Review", "inprogress", "10001"),
    ("Done", "done", "10002"),
    ("Reopened", "todo", "4"),
]
# issue type name -> numeric id (Sub-task detected by name below)
DEFAULT_ISSUE_TYPES = [
    ("Bug", "1"), ("Epic", "2"), ("Improvement", "3"), ("New Feature", "4"),
    ("Story", "5"), ("Task", "6"), ("Sub-task", "7"),
]
SUBTASK_TYPE = "Sub-task"

# Jira DC 기본 우선순위 (name, id). 스킴 자체는 인스턴스마다 다르므로 YAML 로 갈아끼운다.
# 예) P0-Blocker … P4-Trivial / Unclassified 같은 사내 체계.
DEFAULT_PRIORITIES = [
    ("Highest", "1"), ("High", "2"), ("Medium", "3"), ("Low", "4"), ("Lowest", "5"),
]


@dataclass
class Config:
    # network
    host: str = "127.0.0.1"
    port: int = 8080
    latency_ms: int = 0

    # dataset determinism
    seed: str = "0"
    base_date: date = field(default_factory=date.today)

    # project / server identity
    project_key: str = "JIRA820"
    project_name: str = "JIRA820 Sample Project"
    server_version: str = "8.20.8"
    confluence_version: str = "9.2.4"   # linked Confluence DC (CQL 검색 응답 형태 기준)
    bitbucket_version: str = "7.17.2"   # linked Bitbucket DC (code/repo 검색 응답 형태 기준)
    locale: str = "en"  # en | ko

    # custom field ids
    sp_field: str = "customfield_10004"
    epic_link_field: str = "customfield_10008"
    sprint_field: str = "customfield_10007"

    # issue-type name treated as a sub-task (drives the issuetype.subtask boolean)
    subtask_type: str = SUBTASK_TYPE

    # behaviour
    readonly: bool = False
    persist: Optional[str] = None

    # dataset shape (YAML-overridable)
    modules: list = field(default_factory=lambda: list(DEFAULT_MODULES))
    components_extra: list = field(default_factory=lambda: list(DEFAULT_COMPONENTS_EXTRA))
    statuses: list = field(default_factory=lambda: [list(s) for s in DEFAULT_STATUSES])
    # Allowed transitions per status: {"Open": ["In Progress", "Resolved"], ...}.
    # Empty (default) keeps the permissive scheme where any status reaches any other, which is
    # handy for driving a client. Set it to model a real workflow — clients that render a
    # "move to..." menu need this to show only reachable statuses.
    transition_scheme: dict = field(default_factory=dict)
    issue_types: list = field(default_factory=lambda: [list(t) for t in DEFAULT_ISSUE_TYPES])
    priorities: list = field(default_factory=lambda: [list(p) for p in DEFAULT_PRIORITIES])
    # 이슈에 priority 가 없을 때 쓸 기본값. None 이면 목록의 가운데 값.
    default_priority: Optional[str] = None
    # /rest/api/2/myself 가 돌려줄 사용자(=이 세션의 '나'). 실 Jira 는 SSO 로그인 사용자다.
    # world 를 주입해 쓰는 쪽은 자기 사용자로 바꿔야 '내 할 일' 류 화면이 실데이터로 돈다.
    current_user: str = "admin"

    # volume knobs
    epics_per_module: int = 3
    children_per_epic: tuple = (4, 9)
    standalone_per_module: int = 10
    history_per_module: int = 12
    sprints_per_scrum_board: int = 5  # a few closed, one active, a couple future

    # raw yaml passthrough for advanced board/user overrides
    raw: dict = field(default_factory=dict)

    @property
    def components(self) -> list:
        return list(self.modules) + list(self.components_extra)


def _parse_date(v: Any, default: date) -> date:
    if isinstance(v, date):
        return v
    if not v:
        return default
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return default


def load_config() -> Config:
    """Build a Config from JIRA820_CONFIG (YAML) overlaid by JIRA820_* env vars."""
    ycfg: dict = {}
    cfg_path = os.getenv("JIRA820_CONFIG")
    if cfg_path and yaml is not None:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            ycfg = yaml.safe_load(fh) or {}

    c = Config()
    c.raw = ycfg
    c.host = str(_pick("JIRA820_HOST", ycfg.get("host"), c.host))
    c.port = _as_int(_pick("JIRA820_PORT", ycfg.get("port"), c.port), c.port)
    c.latency_ms = _as_int(_pick("JIRA820_LATENCY_MS", ycfg.get("latency_ms"), c.latency_ms), 0)
    c.seed = str(_pick("JIRA820_SEED", ycfg.get("seed"), c.seed))
    c.base_date = _parse_date(_pick("JIRA820_DATE", ycfg.get("date"), None), date.today())
    c.project_key = str(_pick("JIRA820_PROJECT_KEY", ycfg.get("project_key"), c.project_key))
    c.project_name = str(_pick("JIRA820_PROJECT_NAME", ycfg.get("project_name"), c.project_name))
    c.server_version = str(_pick("JIRA820_SERVER_VERSION", ycfg.get("server_version"), c.server_version))
    c.confluence_version = str(_pick("JIRA820_CONFLUENCE_VERSION", ycfg.get("confluence_version"), c.confluence_version))
    c.bitbucket_version = str(_pick("JIRA820_BITBUCKET_VERSION", ycfg.get("bitbucket_version"), c.bitbucket_version))
    c.locale = str(_pick("JIRA820_LOCALE", ycfg.get("locale"), c.locale)).lower()
    c.sp_field = str(_pick("JIRA820_SP_FIELD", ycfg.get("sp_field"), c.sp_field))
    c.epic_link_field = str(_pick("JIRA820_EPIC_LINK_FIELD", ycfg.get("epic_link_field"), c.epic_link_field))
    c.sprint_field = str(_pick("JIRA820_SPRINT_FIELD", ycfg.get("sprint_field"), c.sprint_field))
    c.subtask_type = str(_pick("JIRA820_SUBTASK_TYPE", ycfg.get("subtask_type"), c.subtask_type))
    c.readonly = _as_bool(_pick("JIRA820_READONLY", ycfg.get("readonly"), c.readonly))
    c.persist = _pick("JIRA820_PERSIST", ycfg.get("persist"), None) or None

    if ycfg.get("modules"):
        c.modules = list(ycfg["modules"])
    if ycfg.get("components_extra") is not None:
        c.components_extra = list(ycfg["components_extra"])
    if ycfg.get("statuses"):
        c.statuses = [list(s) for s in ycfg["statuses"]]
    if ycfg.get("transition_scheme"):
        c.transition_scheme = {str(k): list(v) for k, v in ycfg["transition_scheme"].items()}
    if ycfg.get("issue_types"):
        c.issue_types = [list(t) for t in ycfg["issue_types"]]
    if ycfg.get("priorities"):
        c.priorities = [list(p) for p in ycfg["priorities"]]
    if ycfg.get("default_priority"):
        c.default_priority = str(ycfg["default_priority"])
    for k in ("epics_per_module", "standalone_per_module", "history_per_module", "sprints_per_scrum_board"):
        if ycfg.get(k) is not None:
            setattr(c, k, int(ycfg[k]))
    if ycfg.get("children_per_epic"):
        lo, hi = ycfg["children_per_epic"]
        c.children_per_epic = (int(lo), int(hi))
    return c
