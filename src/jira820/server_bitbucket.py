# -*- coding: utf-8 -*-
"""Bitbucket DC 7.17.2 — code/repo 검색 mock.

타겟 두 가지만:
  · repo 검색  : GET  /rest/api/1.0/repos?name=&limit=
  · code 검색  : POST /rest/search/latest/search   {query, entities:{code:{start,limit}}}

repo 응답 형태는 사내 인스턴스로 확인:
  {size,limit,isLastPage,start, values:[{slug,name,state,project:{key,name,type}, links...}]}
code 응답은 공식 문서가 부실 → 소비자(앱)의 dev-tools 프로브 digest 로 필드 확정 예정.
현재는 Bitbucket DC 표준으로 추정한 형태(code.values[].{repository,file,hitContexts}).
"""
from fastapi import APIRouter, Body, Query, Request

router = APIRouter()


def _store(request):
    return request.app.state.store


def _base(request):
    return str(request.base_url).rstrip("/")


def _repo_link(base, pk, slug):
    return {"self": [{"href": f"{base}/projects/{pk}/repos/{slug}/browse"}]}


def _repo_obj(base, r):
    """확인된 repo 형태 + 검색 URL 용 links."""
    p = r["project"]
    return {
        "slug": r["slug"], "id": abs(hash(r["slug"])) % 100000, "name": r["name"],
        "state": r.get("state", "AVAILABLE"), "scmId": "git", "forkable": True, "public": False,
        "project": {"key": p["key"], "id": abs(hash(p["key"])) % 1000,
                    "name": p["name"], "type": p.get("type", "NORMAL"), "public": False},
        "links": _repo_link(base, p["key"], r["slug"]),
    }


@router.get("/rest/api/1.0/repos")
def repos(request: Request, name: str = Query(""), limit: int = Query(25), start: int = Query(0)):
    """전역 저장소 검색 — name 부분일치. 확인된 응답 형태."""
    s = _store(request)
    base = _base(request)
    allr = [r for repos in s.repos.values() for r in repos.values()]
    if name:
        n = name.lower()
        allr = [r for r in allr if n in r["slug"].lower() or n in r["name"].lower()]
    page = allr[start:start + limit]
    return {"size": len(page), "limit": limit, "isLastPage": start + limit >= len(allr),
            "start": start, "values": [_repo_obj(base, r) for r in page]}


def _code_hits(s, query, limit):
    """query 를 파일 내용/경로에서 찾아 code 검색 결과 항목으로. project:/repo: 한정자 지원."""
    import re
    q = query or ""
    proj_f = repo_f = None
    for m in re.finditer(r"(project|repo):(\S+)", q):
        if m.group(1) == "project":
            proj_f = m.group(2)
        else:
            repo_f = m.group(2)
    term = re.sub(r"\b(?:project|repo|ext|lang|path):\S+", "", q).strip().lower()

    hits = []
    for pk, repos in s.repos.items():
        if proj_f and proj_f.lower() != pk.lower():
            continue
        for slug, r in repos.items():
            if repo_f and repo_f.lower() != slug.lower():
                continue
            for f in r.get("files", []):
                path = f["path"]
                lines = f.get("lines", [])
                matched = [(i + 1, ln) for i, ln in enumerate(lines)
                           if not term or term in ln.lower() or term in path.lower()]
                if not matched:
                    continue
                hits.append({
                    "repository": {"slug": r["slug"], "name": r["name"],
                                   "project": {"key": r["project"]["key"],
                                               "name": r["project"]["name"]}},
                    "file": path,
                    "hitContexts": [[{"line": n, "text": t} for n, t in matched[:5]]],
                    "hitCount": len(matched),
                    "pathMatches": [],
                })
                if len(hits) >= limit:
                    return hits
    return hits


@router.post("/rest/search/latest/search")
def code_search(request: Request, payload: dict = Body(default=None)):
    """통합 검색 — code 엔티티만. {query, entities:{code:{start,limit}}}.
    응답: {code:{values,count,isLastPage,start}} (Bitbucket DC 표준 추정)."""
    s = _store(request)
    payload = payload or {}
    query = payload.get("query", "")
    cfg = ((payload.get("entities") or {}).get("code") or {})
    limit = int(cfg.get("limit", 25))
    hits = _code_hits(s, query, limit)
    return {"code": {"category": "code", "isLastPage": True, "count": len(hits),
                     "start": int(cfg.get("start", 0)), "nextStart": None, "values": hits},
            "query": {"substituted": False}}
