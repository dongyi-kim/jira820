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

    def category_of(self, status_name: str) -> str:
        return self.by_name.get(status_name, ("todo", "1"))[0]

    def default_status(self) -> str:
        """First 'todo' status (issue creation lands here)."""
        for name, cat, _sid in self.statuses:
            if cat == "todo":
                return name
        return self.statuses[0][0]

    def available_transitions(self, serializer, current_status: str) -> list:
        out = []
        for name, _cat, _sid in self.statuses:
            if name == current_status:
                continue
            out.append({
                "id": self._tid[name], "name": f"To {name}",
                "to": serializer.status_obj(name),
                "hasScreen": False, "isGlobal": True, "isInitial": False, "isConditional": False,
            })
        return out

    def target_of(self, transition_id: str) -> Optional[str]:
        return self._by_tid.get(str(transition_id))

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
