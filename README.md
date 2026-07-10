# jira-dc-8.20-mock

A **stateful, read + write** mock of **Jira Data Center 8.20.8** — REST v2 plus the Agile
(`/rest/agile/1.0/`) API with real **Scrum sprints and Kanban boards**. It serves a believable,
deterministically-generated project and **accepts mutations** (create / edit / transition / comment /
worklog, move issues between sprints and the backlog), so you can build and test a Jira client
— a ticket **viewer *and* creator** — with no Jira instance, no license, and no database.

```bash
pip install "jira-dc-8.20-mock @ git+https://github.com/dongyi-kim/jira-dc-8.20-mock@v0.1.0"
jira-dc-mock          # -> http://127.0.0.1:8080
```

## Why this exists

New **trial licenses for Jira Data Center are no longer issued**, so standing up the real 8.20.x
server to develop against is impractical (old Docker images exist, but you still need a DC license
key you can't freshly obtain). Existing mocks don't fill the gap either:

| Tool | Stateful data | JQL eval | Epic→children / rollup | Write ops | Agile boards/sprints |
|------|:---:|:---:|:---:|:---:|:---:|
| Mockoon / WireMock / MockServer / Prism | ❌ canned | ❌ | ❌ | ❌ | ❌ |
| `pycontribs/jira` | — (client) | — | — | — | — |
| Atlassian `MockitoContainer` | in-JVM only | ❌ | ❌ | ❌ | ❌ |
| **jira-dc-8.20-mock** | ✅ | ✅ | ✅ | ✅ | ✅ |

Static mock tools replay fixed responses; this one keeps a live, relational, mutable model.

## Run it

```bash
# from PyPI-style git install, or from a checkout:
pip install -e .
jira-dc-mock                      # console script
python -m jira_dc_mock            # module form

JIRAMOCK_PORT=9000 JIRAMOCK_LOCALE=ko JIRAMOCK_SEED=7 jira-dc-mock
JIRAMOCK_CONFIG=examples/config.yaml jira-dc-mock
```

## Configuration (`JIRAMOCK_*` env, overrides `JIRAMOCK_CONFIG` YAML)

| Variable | Default | Purpose |
|---|---|---|
| `JIRAMOCK_HOST` / `JIRAMOCK_PORT` | `127.0.0.1` / `8080` | bind address |
| `JIRAMOCK_LATENCY_MS` | `0` | artificial per-request latency |
| `JIRAMOCK_SEED` | `0` | vary the (deterministic) dataset |
| `JIRAMOCK_DATE` | today | "now" anchor for all relative dates |
| `JIRAMOCK_PROJECT_KEY` / `JIRAMOCK_PROJECT_NAME` | `DEMO` / `Demo Project` | project identity |
| `JIRAMOCK_LOCALE` | `en` | `en` or `ko` text |
| `JIRAMOCK_SP_FIELD` / `JIRAMOCK_EPIC_LINK_FIELD` / `JIRAMOCK_SPRINT_FIELD` | `customfield_10004/10008/10007` | custom field ids |
| `JIRAMOCK_SERVER_VERSION` | `8.20.8` | `serverInfo` version |
| `JIRAMOCK_READONLY` | `false` | reject writes with `403` |
| `JIRAMOCK_PERSIST` | — | JSON file to load/save mutable state across restarts |
| `JIRAMOCK_CONFIG` | — | YAML file for richer overrides (see `examples/config.yaml`) |

Precedence: **env var → YAML → built-in default.** The dataset is deterministic given `(seed, date)`.

## Endpoints

**Read** — `serverInfo`, `myself`, `user`, `field`, `status`, `issuetype`, `priority`, `resolution`,
`project` (+ `/{key}`, `/components`, `/versions`, `/statuses`), `search` (JQL + `fields` projection +
paging), `issue/{key}` (`?expand=changelog`), `issue/{key}/comment`, `issue/{key}/worklog`,
`issue/{key}/transitions`, `issue/createmeta`, `issue/{key}/editmeta`, `activity` (ATOM),
`content/search` (Confluence CQL).

**Write** — `POST issue`, `PUT issue/{key}`, `DELETE issue/{key}`, `POST issue/{key}/transitions`,
`POST/PUT/DELETE issue/{key}/comment[/{id}]`, `POST issue/{key}/worklog`, `PUT issue/{key}/assignee`.

**Agile** (`/rest/agile/1.0/`) — `board` (scrum + kanban), `board/{id}` (+ `/configuration`, `/issue`,
`/backlog`, `/sprint`, `/epic`), `epic/{key}/issue`, `sprint/{id}` (+ `/issue`), `POST sprint`,
`PUT sprint/{id}` (start/complete), `POST sprint/{id}/issue`, `POST backlog/issue`.

Transitions use a permissive open workflow; entering a *done*-category status sets a resolution and
`resolutiondate` (and records a changelog entry), leaving it clears them. A Kanban column move is just
a transition to that column's mapped status.

## Build a client against it

```python
import requests
BASE = "http://127.0.0.1:8080"
# create
key = requests.post(f"{BASE}/rest/api/2/issue",
    json={"fields": {"project": {"key": "DEMO"}, "issuetype": {"name": "Task"},
                     "summary": "Ship the thing"}}).json()["key"]
# move it forward
t = requests.get(f"{BASE}/rest/api/2/issue/{key}/transitions").json()["transitions"][0]["id"]
requests.post(f"{BASE}/rest/api/2/issue/{key}/transitions", json={"transition": {"id": t}})
# drop it into the active sprint
sid = requests.get(f"{BASE}/rest/agile/1.0/board/1/sprint?state=active").json()["values"][0]["id"]
requests.post(f"{BASE}/rest/agile/1.0/sprint/{sid}/issue", json={"issues": [key]})
```

See `examples/curl-examples.sh` for a full shell walk-through.

## Embed / inject your own data

```python
from jira_dc_mock import make_app, build_store, load_config
app = make_app()                       # default seeded store (an ASGI app)
# or inject a custom store implementing the same interface:
# app = make_app(store=my_store)
```

## Develop

```bash
pip install -e ".[test]"
pytest -q
```

## Notes & limits

- The write model is a permissive, single-tenant, in-memory approximation — great for driving a client,
  not a faithful reimplementation of every workflow/permission rule.
- JQL covers common shapes (`=,!=,>=,<=,>,<,IN,~`, `AND`/`OR`, `ORDER BY`, and fields like project,
  assignee, status, statusCategory, type, labels, sprint, and date ranges). Unrecognized clauses are
  ignored rather than erroring.
- Not affiliated with Atlassian. "Jira" is a trademark of Atlassian; this project only emulates the
  public REST shapes for local development and testing.

## License

MIT — see [LICENSE](LICENSE).
