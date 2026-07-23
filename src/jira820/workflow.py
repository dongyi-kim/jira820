"""Workflow: statuses, a permissive (open) transition scheme, and kanban column mapping.

The default workflow is intentionally permissive — any status can transition to any other —
which is convenient for driving a client. Entering a 'done'-category status sets a resolution;
leaving it clears the resolution. Override the status scheme via config.
"""

from __future__ import annotations

from typing import Optional


class Workflow:
    def __init__(self, config):
        self.config = config
        # [(name, category, id)]
        self.statuses = [tuple(s) for s in config.statuses]
        self.by_name = {name: (cat, sid) for name, cat, sid in self.statuses}
        # transition id (stable) per target status
        self._tid = {name: str(11 + i * 10) for i, (name, _c, _s) in enumerate(self.statuses)}
        self._by_tid = {tid: name for name, tid in self._tid.items()}
        # {status: [reachable status, ...]}. Empty means permissive (anything -> anything).
        self.scheme = {k: list(v) for k, v in (getattr(config, "transition_scheme", None) or {}).items()}

    def category_of(self, status_name: str) -> str:
        return self.by_name.get(status_name, ("todo", "1"))[0]

    def default_status(self) -> str:
        """First 'todo' status (issue creation lands here)."""
        for name, cat, _sid in self.statuses:
            if cat == "todo":
                return name
        return self.statuses[0][0]

    # Transition screen fields, mirroring a common Jira DC setup: entering a done-category
    # status opens a screen asking for time spent, assignee and resolution. Clients render
    # this from `?expand=transitions.fields` — without it they cannot know what to ask for.
    RESOLUTIONS = [("1", "Done"), ("2", "Won't Do"), ("3", "Duplicate"), ("4", "Cannot Reproduce")]

    def _screen_fields(self, serializer, target_cat: str) -> dict:
        if target_cat != "done":
            return {}
        return {
            "worklog": {
                "required": True, "name": "Log Work",
                "schema": {"type": "array", "items": "worklog", "system": "worklog"},
                "operations": ["add"], "allowedValues": [],
            },
            "assignee": {
                "required": True, "name": "Assignee",
                "schema": {"type": "user", "system": "assignee"},
                "operations": ["set"], "autoCompleteUrl": "/rest/api/2/user/search?username=",
            },
            "resolution": {
                "required": True, "name": "Resolution",
                "schema": {"type": "resolution", "system": "resolution"},
                "operations": ["set"],
                "allowedValues": [{"id": rid, "name": rname} for rid, rname in self.RESOLUTIONS],
            },
            "comment": {
                "required": False, "name": "Comment",
                "schema": {"type": "comment", "system": "comment"},
                "operations": ["add"], "allowedValues": [],
            },
        }

    def reachable_from(self, current_status: str) -> list:
        """Statuses reachable from `current_status`. Without a scheme every other status is."""
        if not self.scheme:
            return [n for n, _c, _s in self.statuses if n != current_status]
        return [n for n in self.scheme.get(current_status, []) if n in self.by_name]

    def available_transitions(self, serializer, current_status: str, with_fields: bool = False) -> list:
        out = []
        allowed = self.reachable_from(current_status)
        for name, cat, _sid in self.statuses:
            if name == current_status or name not in allowed:
                continue
            t = {
                "id": self._tid[name], "name": f"To {name}",
                "to": serializer.status_obj(name),
                "hasScreen": cat == "done", "isGlobal": True,
                "isInitial": False, "isConditional": False,
            }
            if with_fields:
                t["fields"] = self._screen_fields(serializer, cat)
            out.append(t)
        return out

    def target_of(self, transition_id: str) -> Optional[str]:
        return self._by_tid.get(str(transition_id))

    def is_allowed(self, current_status: str, target: str) -> bool:
        """A transition id alone is not enough — Jira also rejects moves the workflow forbids.
        Without this the mock would accept transitions its own /transitions never offered."""
        return target in self.reachable_from(current_status)

    # ── kanban columns ──
    def kanban_columns(self, serializer) -> list:
        """Default columns grouping statuses by category (Backlog excluded)."""
        groups = [("To Do", "todo"), ("In Progress", "inprogress"), ("Done", "done")]
        cols = []
        for label, cat in groups:
            sids = [sid for name, c, sid in self.statuses if c == cat]
            cols.append({"name": label, "statuses": [{"id": s} for s in sids]})
        return cols

    def status_for_column(self, column_name: str) -> Optional[str]:
        """First status whose category matches the target column."""
        cat = {"to do": "todo", "in progress": "inprogress", "done": "done"}.get(column_name.strip().lower())
        if not cat:
            return None
        for name, c, _sid in self.statuses:
            if c == cat:
                return name
        return None
