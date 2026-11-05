"""Published Confluence DC 9.2.4 state, independent of consumer applications.

This deliberately does not model Synchrony sessions or unpublished shared drafts.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import html
import re
import threading
from datetime import datetime, timezone
from urllib.parse import quote


class ConfluenceError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def _id(value):
    value = str(value or "")
    if not re.fullmatch(r"[0-9]{1,30}", value):
        raise ConfluenceError(400, "Content ID must be numeric")
    return value


def _storage(value):
    if not isinstance(value, dict) or not isinstance(value.get("storage"), dict):
        raise ConfluenceError(400, "body.storage is required")
    text = value["storage"].get("value")
    if not isinstance(text, str) or value["storage"].get("representation", "storage") != "storage":
        raise ConfluenceError(400, "body.storage.value must be storage XHTML")
    return {"storage": {"value": text, "representation": "storage"}}


def _content_payload(value):
    if not isinstance(value, dict):
        raise ConfluenceError(400, "Expected a content object")
    for field in ("space", "container", "version"):
        if field in value and not isinstance(value[field], dict):
            raise ConfluenceError(400, field + " must be an object")
    if "ancestors" in value and (not isinstance(value["ancestors"], list) or
            any(not isinstance(row, dict) or not row.get("id") for row in value["ancestors"])):
        raise ConfluenceError(400, "ancestors must be a list of content IDs")
    if "title" in value and not isinstance(value["title"], str):
        raise ConfluenceError(400, "title must be a string")
    if "position" in value and type(value["position"]) is not int:
        raise ConfluenceError(400, "position must be an integer")
    return value


class ConfluenceState:
    def __init__(self, store):
        self.store, self.lock = store, threading.RLock()
        self.pages, self.versions, self.files, self.file_versions = {}, {}, {}, {}
        self.labels, self.restrictions, self.denied = {}, {}, set()
        self.initialized, self.counter = False, 900000000000
        snapshot = getattr(store, "_confluence_snapshot", None)
        if snapshot:
            self._restore(snapshot)
        store._confluence_state = self

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def writable(self):
        if self.store.config.readonly:
            raise ConfluenceError(403, "Server is read-only")

    def changed(self):
        self.store._touch_persist()

    def seed(self):
        from .serialize import _space_name
        with self.lock:
            if self.initialized:
                return
            originals = self.store.confluence_pages()
            # Explicit records win over synthetic ancestor placeholders regardless of order.
            explicit = {str(row["id"]): row for row in originals}
            for original in originals:
                space, parent, trail = str(original.get("space") or self.store.config.project_key), "", []
                for ancestor in original.get("ancestors") or []:
                    name = ancestor.get("title", "") if isinstance(ancestor, dict) else str(ancestor)
                    trail.append(name)
                    aid = ancestor.get("id") if isinstance(ancestor, dict) else None
                    aid = _id(aid) if aid else str(800000000000 + int(hashlib.sha256((space + "/" + "/".join(trail)).encode()).hexdigest()[:9], 16))
                    if aid not in self.pages and aid not in explicit:
                        self.create({"id": aid, "title": name, "space": {"key": space},
                                     "ancestors": [{"id": parent}] if parent else []})
                    parent = aid
                parent = str(original.get("parentId", parent) or "")
                text = original.get("body") or original.get("title") or ""
                if isinstance(text, dict):
                    body = _storage(text)
                else:
                    text = str(text)
                    body = {"storage": {"value": text if text.lstrip().startswith("<") else
                        "".join("<p>" + html.escape(line.strip()) + "</p>" for line in text.splitlines() if line.strip()) or "<p></p>"}}
                day = original.get("date")
                when = day.isoformat() + "T" + str(original.get("time") or "00:00:00") + "+00:00" if day else self.now()
                self.create({"id": str(original["id"]), "title": original.get("title", ""),
                    "space": {"key": space, "name": _space_name(original, space)},
                    "ancestors": [{"id": parent}] if parent else [], "body": body,
                    "version": {"number": 1, "when": when, "by": {"username": original.get("author", "")}}})
                if original.get("labels"):
                    self.labels[str(original["id"])] = set(original["labels"])
            self.initialized = True

    def create(self, payload):
        _content_payload(payload)
        with self.lock:
            while str(self.counter) in self.pages:
                self.counter += 1
            cid = _id(payload.get("id") or self.counter)
            if cid in self.pages:
                raise ConfluenceError(409, "Content ID already exists")
            self.counter += 1
            kind = payload.get("type", "page")
            if kind not in {"page", "comment", "attachment"}:
                raise ConfluenceError(400, "Unsupported content type")
            parent = str((payload.get("ancestors") or [{}])[-1].get("id") or "")
            container = str((payload.get("container") or {}).get("id") or "")
            target = self.pages.get(container or parent) or {}
            space = (payload.get("space") or {}).get("key") or (target.get("space") or {}).get("key") or self.store.config.project_key
            row = {"id": cid, "type": kind, "status": "current", "title": payload.get("title", ""),
                "space": {"key": str(space), "name": (payload.get("space") or {}).get("name") or str(space), "type": "global"},
                "parent": parent, "position": payload.get("position", len(self.pages)),
                "container": {"id": container, "type": "page"} if container else {},
                "version": {"number": 1, "when": self.now(), "by": {"username": self.store.config.current_user}, **payload.get("version", {})},
                "body": _storage(payload.get("body") or {"storage": {"value": ""}})}
            if row["version"]["number"] != 1:
                raise ConfluenceError(400, "New content starts at version 1")
            row["history"] = {"createdDate": row["version"]["when"], "createdBy": copy.deepcopy(row["version"]["by"])}
            self.pages[cid], self.versions[cid] = row, {1: copy.deepcopy(row)}
            return row

    def _allowed(self, row):
        cursor, seen = row, set()
        while cursor:
            cid = cursor["id"]
            if cid in self.denied:
                return False
            if cid in seen:
                raise ConfluenceError(409, "Content hierarchy has a cycle")
            seen.add(cid)
            cursor = self.pages.get(cursor.get("parent") or (cursor.get("container") or {}).get("id"))
        return True

    def _container_current(self, row):
        parent, seen = row.get("parent") or (row.get("container") or {}).get("id"), {row["id"]}
        while parent:
            if parent in seen:
                raise ConfluenceError(409, "Content hierarchy has a cycle")
            seen.add(parent)
            item = self.pages.get(parent)
            if not item or item["status"] != "current":
                return False
            parent = item.get("parent") or (item.get("container") or {}).get("id")
        return True

    def get(self, cid, *, status="current", version=None):
        self.seed()
        cid = str(cid)
        row = self.pages.get(cid)
        if row and not self._allowed(row):
            raise ConfluenceError(403, "No permission to view this document")
        if not row or (status and row["status"] != status) or not self._container_current(row):
            raise ConfluenceError(404, "No content found with id : " + cid)
        if version is not None:
            row = self.versions[cid].get(int(version))
            if row is None:
                raise ConfluenceError(404, "Content version not found")
        return row

    def ancestors(self, row):
        values, seen = [], {row["id"]}
        parent = row.get("parent")
        while parent:
            if parent in seen:
                raise ConfluenceError(409, "Content hierarchy has a cycle")
            seen.add(parent)
            item = self.pages.get(parent)
            if not item:
                break
            values.insert(0, {"id": parent, "title": item["title"], "type": "page"})
            parent = item.get("parent")
        return values

    def validate_parent(self, page, parent):
        if not parent:
            return
        target = self.get(_id(parent))
        if target["type"] != "page" or target["space"]["key"] != page["space"]["key"]:
            raise ConfluenceError(400, "Parent must be a page in the same Space")
        if str(parent) == page["id"] or page["id"] in [row["id"] for row in self.ancestors(target)]:
            raise ConfluenceError(409, "Cannot move a page below itself")

    def update(self, cid, payload):
        _content_payload(payload)
        with self.lock:
            self.writable()
            row = self.get(cid, status=None)
            version = (payload.get("version") or {}).get("number")
            if type(version) is not int or version != row["version"]["number"] + 1:
                raise ConfluenceError(409, "Version conflict")
            if payload.get("status", "current") not in {"current", "trashed"}:
                raise ConfluenceError(400, "Unpublished drafts are not modeled")
            if payload.get("type", row["type"]) != row["type"]:
                raise ConfluenceError(400, "Content type cannot change")
            if (payload.get("space") or {}).get("key", row["space"]["key"]) != row["space"]["key"]:
                raise ConfluenceError(400, "Cross-Space changes are not modeled")
            candidate = copy.deepcopy(row)
            if "title" in payload:
                if row["type"] == "page" and not str(payload["title"]).strip():
                    raise ConfluenceError(400, "Page title is required")
                candidate["title"] = payload["title"]
            for field in ("status", "position"):
                if field in payload:
                    candidate[field] = payload[field]
            if "body" in payload:
                candidate["body"] = _storage(payload["body"])
            if "ancestors" in payload:
                candidate["parent"] = str((payload["ancestors"] or [{}])[-1].get("id") or "")
                self.validate_parent(candidate, candidate["parent"])
            candidate["version"] = {**payload["version"], "when": self.now(), "by": {"username": self.store.config.current_user}}
            authors = [*row.get("contributors", []), row["version"]["by"], candidate["version"]["by"]]
            candidate["contributors"] = list({item.get("username", ""): item for item in authors}.values())
            self.pages[str(cid)] = candidate
            self.versions[str(cid)][version] = copy.deepcopy(candidate)
            self.changed()
            return candidate

    def content(self, row, base="", expand=""):
        data = copy.deepcopy(row)
        cid = row["id"]
        data.pop("parent", None)
        want = {item.strip().removeprefix("content.") for item in expand.split(",")}
        if "ancestors" in want:
            data["ancestors"] = self.ancestors(row)
        data["_links"] = {"webui": f"/spaces/{row['space']['key']}/pages/{cid}", "self": base + f"/rest/api/content/{cid}"}
        if row["type"] == "attachment":
            data["_links"]["download"] = f"/download/attachments/{row['container']['id']}/{quote(row['title'], safe='')}"
            content, mime = self.file_versions.get(cid, {}).get(row["version"]["number"], self.files.get(cid, (b"", "application/octet-stream")))
            data["extensions"] = {"fileSize": len(content), "mediaType": mime}
        reps = {rep for rep in ("storage", "view") if "body" in want or "body." + rep in want}
        if reps:
            data["body"] = {rep: {"value": row["body"]["storage"]["value"], "representation": rep} for rep in reps}
        else:
            data.pop("body", None)
        return data

    def search(self, query):
        from .cql import filter_content
        self.seed()
        with self.lock:
            rows = [copy.deepcopy(row) for row in self.pages.values() if row["status"] == "current"
                    and self._allowed(row) and self._container_current(row)]
        try:
            return filter_content(rows, query, today=self.store.config.base_date,
                current_user=self.store.config.current_user, ancestor_resolver=self.ancestors,
                labels_resolver=lambda row: self.labels.get(row["id"], set()))
        except ValueError as exc:
            raise ConfluenceError(400, str(exc)) from exc

    def snapshot(self):
        with self.lock:
            return {"pages": copy.deepcopy(self.pages), "versions": copy.deepcopy(self.versions),
                "files": {key: [base64.b64encode(data).decode("ascii"), mime] for key, (data, mime) in self.files.items()},
                "fileVersions": {key: {str(v): [base64.b64encode(data).decode("ascii"), mime]
                    for v, (data, mime) in versions.items()} for key, versions in self.file_versions.items()},
                "labels": {key: sorted(values) for key, values in self.labels.items()},
                "restrictions": copy.deepcopy(self.restrictions), "denied": sorted(self.denied),
                "initialized": self.initialized, "counter": self.counter}

    def _restore(self, data):
        self.pages = copy.deepcopy(data.get("pages", {}))
        self.versions = {key: {int(v): row for v, row in rows.items()} for key, rows in data.get("versions", {}).items()}
        self.files = {key: (base64.b64decode(value[0]), value[1]) for key, value in data.get("files", {}).items()}
        self.file_versions = {key: {int(v): (base64.b64decode(value[0]), value[1]) for v, value in rows.items()}
                              for key, rows in data.get("fileVersions", {}).items()}
        self.labels = {key: set(values) for key, values in data.get("labels", {}).items()}
        self.restrictions, self.denied = data.get("restrictions", {}), set(data.get("denied", []))
        self.initialized, self.counter = data.get("initialized", True), data.get("counter", 900000000000)
