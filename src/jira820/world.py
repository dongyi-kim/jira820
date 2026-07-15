"""Deterministic seed data generator.

Populates a Store with a believable project: users, an Epic -> Story/Task/Bug -> Sub-task
hierarchy, comments, worklogs, versions, activity, Confluence pages, and Agile boards
(one Scrum board with sprints + one Kanban board). Fully deterministic given (seed, base_date).
"""

from __future__ import annotations

import hashlib
import random
from datetime import timedelta

from . import content as content_mod

STORYLIKE = {"Story", "Task", "Improvement", "New Feature"}
CHILD_TYPES = ["Story", "Task", "Bug", "Improvement", "New Feature"]
CHILD_WEIGHTS = [6, 4, 2, 2, 1]


def _rng(*parts):
    seed = int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)
    return random.Random(seed)


def _shash(s: str) -> int:
    h = 0
    for ch in str(s):
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return h


def _cat(rng, maturity):
    return "done" if rng.random() < maturity else ("inprogress" if rng.random() < 0.5 else "todo")


def seed(store) -> None:
    Seeder(store).run()


class Seeder:
    def __init__(self, store):
        self.store = store
        self.c = store.config
        self.wf = store.workflow
        self.txt = content_mod.get(self.c.locale)
        self.today = self.c.base_date
        self._counter = 0
        # status names by category (for picking a concrete statusName from a category)
        self._status_by_cat = {}
        for name, cat, _sid in self.c.statuses:
            self._status_by_cat.setdefault(cat, []).append(name)

    # ── helpers ──
    def _newkey(self):
        self._counter += 1
        return f"{self.c.project_key}-{self._counter}"

    def _status_name(self, rng, cat):
        return rng.choice(self._status_by_cat.get(cat) or [self.wf.default_status()])

    def _tm(self, rng):
        return "%02d:%02d" % (rng.randint(8, 19), rng.choice([0, 10, 15, 20, 30, 45]))

    # ── users ──
    def _make_users(self):
        users = {"admin": {"name": "admin", "displayName": "Administrator",
                           "realName": "Administrator", "company": ""}}
        modules = self.c.modules
        per = max(2, (self.c.raw.get("users_per_module") or 3))
        module_users = {}
        n = 0
        for m in modules:
            ids = []
            for _ in range(per):
                n += 1
                uid = "u%02d" % n
                h = _shash(uid + self.c.seed)
                nm = self._person_name(h)
                co = self.txt.COMPANIES[(h // 3) % len(self.txt.COMPANIES)]
                dn = f"{nm} {co}".strip()
                users[uid] = {"name": uid, "displayName": dn, "realName": nm, "company": co}
                ids.append(uid)
            module_users[m] = ids
        self.store.module_users = module_users
        return users

    def _person_name(self, h):
        fn = self.txt.FIRST_NAMES[h % len(self.txt.FIRST_NAMES)]
        ln = self.txt.LAST_NAMES[(h // 7) % len(self.txt.LAST_NAMES)]
        # Korean: {last}{first}; English: {first} {last}
        return f"{ln}{fn}" if self.c.locale == "ko" else f"{fn} {ln}"

    def _pool(self, module):
        return self.store.module_users.get(module) or ["admin"]

    # ── issue factory ──
    def _summary(self, rng, itype, module):
        pool = self.txt.SUMMARY.get(itype, ["Work item"])
        return f"[{module}] " + rng.choice(pool)

    def _description(self, rng, itype, module):
        t = self.txt.DESCRIPTION
        if itype == "Bug":
            return t["Bug"].replace("[env]", "[env]").format(steps=rng.choice(self.txt.BUG_STEPS))
        if itype == "Story":
            return t["Story"].format(role=rng.choice(self.txt.ROLES), goal=rng.choice(self.txt.STORY_GOALS),
                                     benefit=rng.choice(self.txt.BENEFITS),
                                     ac1=rng.choice(self.txt.ACS), ac2=rng.choice(self.txt.ACS))
        if itype == "Task":
            return t["Task"].format(item=rng.choice(self.txt.TASK_ITEMS))
        return t["_default"].format(module=module)

    def _make_issue(self, rng, itype, module, epic_key=None, parent_key=None,
                    component=None, created=None, resolved=None, force_cat=None):
        pool = self._pool(module)
        assignee = pool[rng.randrange(len(pool))]
        reporter = rng.choice(["admin"] + pool)
        maturity = rng.uniform(0.15, 0.85)
        created = created or (self.today - timedelta(days=rng.randint(5, 175)))
        if resolved is not None:
            cat = "done"
        else:
            cat = force_cat or _cat(rng, maturity)
            if cat == "done":
                span = max((self.today - created).days, 1)
                resolved = created + timedelta(days=rng.randint(1, span))
        updated = resolved or (created + timedelta(days=rng.randint(0, max((self.today - created).days, 1))))
        if updated > self.today:
            updated = self.today
        due = None if rng.random() < 0.25 else (created + timedelta(days=rng.randint(40, 160)))
        status_name = self._status_name(rng, cat)

        if itype in STORYLIKE:
            sp = None if rng.random() < 0.12 else rng.choice([1, 2, 3, 5, 8])
        elif itype == "Bug":
            sp = 0
        else:
            sp = None

        key = self._newkey()
        # comments
        ncom = rng.randint(0, 3) if itype != "Sub-task" else rng.randint(0, 1)
        comments = []
        for _ in range(ncom):
            kind, tmpl = rng.choice(self.txt.COMMENT_TYPES)
            author = rng.choice(pool + ["admin"])
            ccreated = self.today - timedelta(days=rng.randint(0, 13))
            text = tmpl.format(a=self.store_display(author), m=rng.choice(self.c.modules),
                               who=self.store_display(rng.choice(pool)))
            comments.append({"author": author, "kind": kind, "text": text, "body": text,
                             "created": ccreated, "tcreated": self._tm(rng),
                             "id": f"{key}-c{len(comments)}"})
        # worklog
        worklog = []
        if cat != "todo":
            for _ in range(rng.randint(0, 3)):
                worklog.append({"author": assignee,
                                "date": self.today - timedelta(days=rng.randint(0, 7)),
                                "time": self._tm(rng),
                                "seconds": 3600 * rng.randint(1, 6)})
        # changelog: a transition entry if it left 'todo'
        changelog = []
        if cat != "todo":
            changelog.append({"author": assignee, "date": updated, "time": self._tm(rng),
                              "items": [{"field": "status", "fieldtype": "jira",
                                         "from": "1", "fromString": self.wf.default_status(),
                                         "to": self.wf.by_name.get(status_name, ("", "1"))[1],
                                         "toString": status_name}]})

        self.store.issues[key] = {
            "key": key, "project": self.c.project_key, "type": itype,
            "summary": self._summary(rng, itype, module),
            "description": self._description(rng, itype, module),
            "module": module, "component": component or module,
            "assignee": assignee, "reporter": reporter,
            "statusCategory": cat, "statusName": status_name,
            "resolution": "Done" if cat == "done" else None,
            "labels": (["mock"] if itype in STORYLIKE and rng.random() < 0.12 else []),
            "sp": sp, "epicKey": epic_key if itype != "Epic" else None, "parentKey": parent_key,
            "created": created, "updated": updated, "resolved": resolved, "due": due,
            "tcreated": self._tm(rng), "tupdated": self._tm(rng), "tresolved": self._tm(rng),
            "comments": comments, "worklog": worklog, "subtasks": [],
            "sprints": [], "fixVersions": [], "changelog": changelog,
            "watches": rng.randint(0, 4), "votes": rng.randint(0, 3),
        }
        return key

    def store_display(self, uid):
        return (self.store.users.get(uid) or {}).get("realName") or uid

    def _add_subtasks(self, rng, parent_key, module, n):
        for _ in range(n):
            sk = self._make_issue(rng, "Sub-task", module, parent_key=parent_key)
            self.store.issues[parent_key]["subtasks"].append(sk)

    # ── build ──
    def run(self):
        self.store.users = self._make_users()
        self._build_epics()
        self._build_standalone()
        self._build_history()
        self._build_versions()
        self._build_boards_sprints()
        self.store.reindex()
        self._build_activity()
        self._build_confluence()

    def _build_epics(self):
        for module in self.c.modules:
            for e in range(self.c.epics_per_module):
                rng = _rng(self.c.seed, "epic", module, e)
                ek = self._make_issue(rng, "Epic", module)
                lo, hi = self.c.children_per_epic
                for _ in range(rng.randint(lo, hi)):
                    ct = rng.choices(CHILD_TYPES, weights=CHILD_WEIGHTS)[0]
                    ck = self._make_issue(rng, ct, module, epic_key=ek)
                    if ct in STORYLIKE and rng.random() < 0.4:
                        self._add_subtasks(rng, ck, module, rng.randint(1, 2))

    def _build_standalone(self):
        for module in self.c.modules:
            rng = _rng(self.c.seed, "solo", module)
            for _ in range(self.c.standalone_per_module):
                ct = rng.choices(CHILD_TYPES, weights=CHILD_WEIGHTS)[0]
                comp = "Support" if (rng.random() < 0.15 and "Support" in self.c.components) else module
                ck = self._make_issue(rng, ct, module, component=comp)
                if ct in STORYLIKE and rng.random() < 0.3:
                    self._add_subtasks(rng, ck, module, rng.randint(1, 2))

    def _build_history(self):
        for module in self.c.modules:
            rng = _rng(self.c.seed, "hist", module)
            for _ in range(self.c.history_per_module):
                created = self.today - timedelta(days=rng.randint(30, 180))
                resolved = created + timedelta(days=rng.randint(1, 25))
                if resolved > self.today:
                    resolved = self.today
                self._make_issue(rng, rng.choices(CHILD_TYPES, weights=CHILD_WEIGHTS)[0],
                                 module, created=created, resolved=resolved)

    def _build_versions(self):
        self.store.versions = [
            {"id": 10100, "name": "1.0", "released": True,
             "releaseDate": (self.today - timedelta(days=40)).isoformat()},
            {"id": 10101, "name": "1.1", "released": False, "releaseDate": None},
        ]
        rng = _rng(self.c.seed, "versions")
        for it in self.store.issues.values():
            if it["type"] in STORYLIKE and rng.random() < 0.4:
                it["fixVersions"] = [rng.choice(self.store.versions)]

    def _build_boards_sprints(self):
        pk = self.c.project_key
        scrum_id, kanban_id = 1, 2
        self.store.boards = {
            scrum_id: {"id": scrum_id, "name": f"{pk} Scrum", "type": "scrum",
                       "projectKey": pk, "filterId": 10001},
            kanban_id: {"id": kanban_id, "name": f"{pk} Kanban", "type": "kanban",
                        "projectKey": pk, "filterId": 10002},
        }
        # sprints for the scrum board
        n = self.c.sprints_per_scrum_board
        self.store.sprints = {}
        rng = _rng(self.c.seed, "sprints")
        sid = 0
        # (n-3) closed, 1 active, 2 future — clamped
        n_closed = max(0, n - 3)
        for i in range(n):
            sid += 1
            if i < n_closed:
                state = "closed"
                start = self.today - timedelta(days=(n_closed - i) * 14 + 14)
                end = start + timedelta(days=14)
                complete = end
            elif i == n_closed:
                state = "active"
                start = self.today - timedelta(days=7)
                end = self.today + timedelta(days=7)
                complete = None
            else:
                state = "future"
                start = self.today + timedelta(days=(i - n_closed) * 14)
                end = start + timedelta(days=14)
                complete = None
            self.store.sprints[sid] = {
                "id": sid, "name": f"{pk} Sprint {sid}", "state": state, "boardId": scrum_id,
                "goal": rng.choice(self.txt.SPRINT_GOALS),
                "startDate": start, "endDate": end, "completeDate": complete,
            }
        # assign issues to sprints: done -> closed, inprogress -> active, todo -> active/future
        closed = [s for s in self.store.sprints.values() if s["state"] == "closed"]
        active = [s for s in self.store.sprints.values() if s["state"] == "active"]
        future = [s for s in self.store.sprints.values() if s["state"] == "future"]
        for it in self.store.issues.values():
            if it["type"] in ("Epic", "Sub-task"):
                continue
            r = _rng(self.c.seed, "sprintassign", it["key"])
            if it["statusCategory"] == "done" and closed:
                it["sprints"] = [r.choice(closed)["id"]]
            elif it["statusCategory"] == "inprogress" and active:
                it["sprints"] = [active[0]["id"]]
            elif it["statusCategory"] == "todo" and r.random() < 0.5:
                pick = active + future
                if pick:
                    it["sprints"] = [r.choice(pick)["id"]]

    def _build_activity(self):
        ev = {}

        def add(user, d, t, kind, key, summary):
            ev.setdefault(user, []).append({"date": d, "time": t, "kind": kind, "key": key, "summary": summary})

        for it in self.store.issues.values():
            add(it["reporter"], it["created"], it.get("tcreated"), "created", it["key"], it["summary"])
            for c in it["comments"]:
                add(c["author"], c["created"], c.get("tcreated"), "commented", it["key"], it["summary"])
            for w in it["worklog"]:
                add(w["author"], w["date"], w.get("time"), "logged work", it["key"], it["summary"])
            if it["resolved"]:
                add(it["assignee"], it["resolved"], it.get("tresolved"), "resolved", it["key"], it["summary"])
        for u in ev:
            ev[u].sort(key=lambda e: (e["date"].isoformat(), e.get("time") or ""), reverse=True)
        self.store.activity = ev

    def _build_confluence(self):
        conf = {}
        for module, ids in self.store.module_users.items():
            for uid in ids:
                rng = _rng(self.c.seed, "conf", uid)
                pages = []
                for _ in range(rng.randint(0, 4)):
                    _t = rng.choice(self.txt.CONF_TITLES)
                    pages.append({"title": _t,
                                  "space": rng.choice(self.txt.CONF_SPACES),
                                  "action": rng.choice(self.txt.CONF_ACTIONS),
                                  "body": "%s. %s" % (_t, rng.choice(self.txt.CONF_TITLES)),
                                  "date": self.today - timedelta(days=rng.randint(0, 13)),
                                  "time": self._tm(rng)})
                pages.sort(key=lambda p: p["date"], reverse=True)
                conf[uid] = pages
        self.store.confluence = conf
