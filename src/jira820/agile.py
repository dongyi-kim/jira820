"""Agile board read-model: which issues belong to a board, its backlog, sprints, epics, columns.

Boards filter on the project. Scrum backlog = board issues not in an active/future sprint.
Kanban board issues = all non-subtask issues; columns map to statuses (see workflow.kanban_columns).
"""

from __future__ import annotations


def _board_issue_keys(store, board_id: int) -> list:
    board = store.boards.get(board_id)
    if not board:
        return []
    pk = board["projectKey"]
    keys = [k for k, it in store.issues.items()
            if it["project"] == pk and it["type"] not in ("Epic", "Sub-task")]
    keys.sort()
    return keys


def board_issue_keys(store, board_id: int) -> list:
    return _board_issue_keys(store, board_id)


def backlog_keys(store, board_id: int) -> list:
    """Issues not currently in an active/future sprint (and not done)."""
    active_future = {s["id"] for s in store.sprints.values()
                     if s["boardId"] == board_id and s["state"] in ("active", "future")}
    out = []
    for k in _board_issue_keys(store, board_id):
        it = store.issues[k]
        in_open_sprint = any(sid in active_future for sid in it.get("sprints", []))
        if not in_open_sprint and it["statusCategory"] != "done":
            out.append(k)
    return out


def board_sprint_ids(store, board_id: int) -> list:
    ids = [sid for sid, s in store.sprints.items() if s["boardId"] == board_id]
    ids.sort()
    return ids


def board_epic_keys(store, board_id: int) -> list:
    board = store.boards.get(board_id)
    if not board:
        return []
    pk = board["projectKey"]
    return sorted(k for k, it in store.issues.items() if it["project"] == pk and it["type"] == "Epic")


def sprint_issue_keys(store, sid: int) -> list:
    return sorted(k for k, it in store.issues.items() if sid in it.get("sprints", []))


def board_json(store, board_id: int, base_url: str) -> dict:
    b = store.boards[board_id]
    return {"id": b["id"], "self": f"{base_url}/rest/agile/1.0/board/{b['id']}",
            "name": b["name"], "type": b["type"],
            "location": {"projectKey": b["projectKey"], "projectName": store.config.project_name,
                         "projectTypeKey": "software"}}


def board_configuration(store, board_id: int, base_url: str) -> dict:
    b = store.boards[board_id]
    ser = store.serializer
    columns = store.workflow.kanban_columns(ser)
    return {
        "id": b["id"], "name": b["name"], "type": b["type"],
        "self": f"{base_url}/rest/agile/1.0/board/{b['id']}/configuration",
        "location": {"type": "project", "key": b["projectKey"]},
        "filter": {"id": str(b["filterId"]), "self": f"{base_url}/rest/api/2/filter/{b['filterId']}"},
        "columnConfig": {"constraintType": "issueCount", "columns": columns},
        "estimation": {"type": "field",
                       "field": {"fieldId": store.config.sp_field, "displayName": "Story Points"}},
        "ranking": {"rankCustomFieldId": 10005},
    }
