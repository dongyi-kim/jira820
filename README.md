# jira820

**Jira Data Center 8.20.8** 을 로컬에서 흉내 내는 **상태형(stateful) 읽기+쓰기 mock 서버**입니다.
REST v2 는 물론 Agile(`/rest/agile/1.0/`) API 까지 — **실제 Scrum 스프린트와 Kanban 보드**를 포함합니다.
결정적으로 생성된 그럴듯한 프로젝트 데이터를 서빙하고 **변경(생성/수정/전이/코멘트/워크로그, 스프린트·백로그
이동)까지 받아들이므로**, Jira 인스턴스·라이선스·DB 없이 **티켓 뷰어 *및* 작성 클라이언트**를 개발·테스트할 수 있습니다.

**연동 제품 버전(고정):** Jira DC **8.20.8** · Confluence DC **9.2.4** · Bitbucket DC **7.17.2**.
CQL 검색(`/rest/api/search`) 응답은 이 Confluence 9.2.4 형태를 따릅니다.
버전 표기는 `JIRA820_CONFLUENCE_VERSION` / `JIRA820_SERVER_VERSION` 으로 바꿀 수 있습니다.

또한 **통합 검색**(JQL `text ~`, Confluence CQL 검색)과 **멀티 프로젝트/스페이스**(소비자가 자체
데이터를 additive 주입)를 지원합니다.

```bash
pip install jira820
jira820                       # -> http://127.0.0.1:8080  (브라우저 열면 데모 UI)
```

## 데모 웹 UI

`jira820` 를 실행하고 **http://127.0.0.1:8080/** 를 브라우저로 열면 내장 데모 클라이언트가 뜹니다
(같은 오리진이라 CORS 없음). 티켓 **보기·검색(JQL)·생성·속성 수정·상태 전이·코멘트·파일/이미지 업로드**를
바로 해볼 수 있습니다 — REST API 사용 예시이자, 직접 만들 클라이언트의 출발점입니다. 소스: [`demo/index.html`](demo/index.html)
(빌드 불필요한 단일 파일 바닐라 JS).

## 왜 만들었나

Jira **Data Center 는 신규 트라이얼 라이선스 발급이 중단**되어, 개발 대상인 실제 8.20.x 서버를 새로 띄우기가
현실적으로 어렵습니다(구 Docker 이미지는 있으나 새로 발급 못 받는 DC 라이선스 키가 필요). 기존 목(mock) 도구들도
이 공백을 못 메웁니다:

| 도구 | 상태 유지 | JQL 평가 | Epic→자식/롤업 | 쓰기 | Agile 보드/스프린트 |
|------|:---:|:---:|:---:|:---:|:---:|
| Mockoon / WireMock / MockServer / Prism | ❌ 고정응답 | ❌ | ❌ | ❌ | ❌ |
| `pycontribs/jira` | — (클라이언트) | — | — | — | — |
| Atlassian `MockitoContainer` | JVM 내부만 | ❌ | ❌ | ❌ | ❌ |
| **jira820** | ✅ | ✅ | ✅ | ✅ | ✅ |

정적 목 도구는 고정 응답을 재생할 뿐이고, 이 프로젝트는 **살아있는 관계형·가변 데이터 모델**을 유지합니다.

## 실행

```bash
pip install -e .                 # 체크아웃에서
jira820                          # 콘솔 스크립트
python -m jira820                # 모듈 형태

JIRA820_PORT=9000 JIRA820_LOCALE=ko JIRA820_SEED=7 jira820
JIRA820_CONFIG=examples/config.yaml jira820
```

## 설정 (`JIRA820_*` 환경변수 > `JIRA820_CONFIG` YAML > 기본값)

| 변수 | 기본값 | 용도 |
|---|---|---|
| `JIRA820_HOST` / `JIRA820_PORT` | `127.0.0.1` / `8080` | 바인드 주소 |
| `JIRA820_LATENCY_MS` | `0` | 요청당 인위적 지연(캐시/성능 테스트) |
| `JIRA820_SEED` | `0` | (결정적) 데이터셋 변주 |
| `JIRA820_DATE` | 오늘 | 모든 상대 날짜의 "오늘" 기준 |
| `JIRA820_PROJECT_KEY` / `JIRA820_PROJECT_NAME` | `JIRA820` / `JIRA820 Sample Project` | 기본 샘플 프로젝트 식별 |
| `JIRA820_CONFLUENCE_VERSION` | `9.2.4` | 연동 Confluence DC 버전(CQL 검색 응답 형태) |
| `JIRA820_LOCALE` | `en` | `en` 또는 `ko` |
| `JIRA820_SP_FIELD` / `JIRA820_EPIC_LINK_FIELD` / `JIRA820_SPRINT_FIELD` | `customfield_10004/10008/10007` | 커스텀필드 id |
| `JIRA820_SUBTASK_TYPE` | `Sub-task` | `issuetype.subtask` 판정에 쓰는 서브태스크 타입명 |
| `JIRA820_SERVER_VERSION` | `8.20.8` | `serverInfo` 버전 |
| `JIRA820_READONLY` | `false` | 쓰기를 `403` 으로 차단 |
| `JIRA820_PERSIST` | — | 가변 상태를 JSON 파일로 로드/저장(재시작 간 유지) |
| `JIRA820_CONFIG` | — | 더 풍부한 커스터마이즈 YAML (`examples/config.yaml` 참고) |

우선순위는 **환경변수 → YAML → 기본값**. 데이터셋은 `(seed, date)` 가 같으면 항상 동일합니다.

## 엔드포인트

**읽기** — `serverInfo`, `myself`, `user`, `field`, `status`, `issuetype`, `priority`, `resolution`,
`project`(+`/{key}`, `/components`, `/versions`, `/statuses`), `search`(JQL + `fields` 투영 + 페이징),
`issue/{key}`(`?expand=changelog`), `issue/{key}/comment`, `issue/{key}/worklog`, `issue/{key}/transitions`,
`issue/createmeta`, `issue/{key}/editmeta`, `issueLinkType`, `activity`(ATOM), `content/search`(Confluence CQL).
이슈는 `fields.issuelinks` 로 **이슈 링크**(relates to / blocks / duplicates / clones)를 제공합니다 — 상대 이슈는 `inwardIssue`/`outwardIssue` 로 방향까지 구분됩니다.

**쓰기** — `POST issue`, `PUT issue/{key}`, `DELETE issue/{key}`, `POST issue/{key}/transitions`,
`POST/PUT/DELETE issue/{key}/comment[/{id}]`, `POST issue/{key}/worklog`, `PUT issue/{key}/assignee`.

**첨부파일/이미지** — `POST issue/{key}/attachments`(멀티파트, 필드명 `file`, 다중 가능),
`GET/DELETE rest/api/2/attachment/{id}`, `GET /secure/attachment/{id}/{filename}`(원본 다운로드),
`GET /secure/thumbnail/{id}/{filename}`. 업로드한 파일은 `fields.attachment[]` 에 나타납니다.

> **설명·코멘트에 이미지/파일 넣기**: 먼저 위 `attachments` 로 업로드한 뒤, 설명/코멘트 body 에 Jira 위키 마크업
> `!diagram.png|thumbnail!`(이미지) 또는 `[^spec.pdf]`(파일)로 참조하세요 — 실제 Jira 와 동일한 흐름입니다.

**Agile** (`/rest/agile/1.0/`) — `board`(scrum+kanban), `board/{id}`(+`/configuration`, `/issue`, `/backlog`,
`/sprint`, `/epic`), `epic/{key}/issue`, `sprint/{id}`(+`/issue`), `POST sprint`, `PUT sprint/{id}`(시작/완료),
`POST sprint/{id}/issue`, `POST backlog/issue`.

전이(transition)는 관대한 오픈 워크플로입니다. *done* 카테고리 상태로 들어가면 resolution 과 `resolutiondate` 가
세팅되고 changelog 가 기록되며, 벗어나면 해제됩니다. **Kanban 컬럼 이동 = 그 컬럼에 매핑된 상태로의 전이**입니다.

## 클라이언트에서 사용

```python
import requests
BASE = "http://127.0.0.1:8080"
# 생성
key = requests.post(f"{BASE}/rest/api/2/issue",
    json={"fields": {"project": {"key": "JIRA820"}, "issuetype": {"name": "Task"},
                     "summary": "무언가 배포"}}).json()["key"]
# 전이
t = requests.get(f"{BASE}/rest/api/2/issue/{key}/transitions").json()["transitions"][0]["id"]
requests.post(f"{BASE}/rest/api/2/issue/{key}/transitions", json={"transition": {"id": t}})
# 활성 스프린트로 이동
sid = requests.get(f"{BASE}/rest/agile/1.0/board/1/sprint?state=active").json()["values"][0]["id"]
requests.post(f"{BASE}/rest/agile/1.0/sprint/{sid}/issue", json={"issues": [key]})
```

전체 셸 예시는 `examples/curl-examples.sh` 를 보세요.

## 내 데이터 주입(임베드)

```python
from jira820 import make_app, build_store
from jira820.config import Config
from jira820.store import Store

app = make_app()                       # 기본 시드 스토어(ASGI 앱)
# 또는 외부 데이터 주입: 빈 스토어를 만들고 채워서 넘김
store = Store(Config(project_key="DL"), seed=False)
store.issues = my_issues; store.users = my_users; store.reindex()
app = make_app(store=store)            # 이 패키지의 직렬화기/엔드포인트를 그대로 재사용
```

## 개발

```bash
pip install -e ".[test]"
pytest -q
```

## 참고 / 한계

- 쓰기 모델은 관대한 단일 테넌트 인메모리 근사입니다 — 클라이언트 구동엔 훌륭하지만 모든 워크플로/권한 규칙을
  충실히 재현하진 않습니다.
- JQL 은 흔한 형태(`=,!=,>=,<=,>,<,IN,~`, `AND`/`OR`, `ORDER BY`, project/assignee/status/statusCategory/type/
  labels/sprint/날짜범위, `text ~` 전문검색)를 지원하며, 인식하지 못한 절은 오류 대신 무시합니다.
- Confluence CQL(`space`/`title`/`text`/`siteSearch`/`contributor`/`lastmodified`)은 검색 응답용 subset 만
  지원합니다(연동 Confluence DC 9.2.4 형태). 인식 못한 절은 무시합니다.
- Atlassian 과 무관합니다. "Jira" 는 Atlassian 의 상표이며, 이 프로젝트는 로컬 개발·테스트를 위해 공개 REST 형태만
  흉내 냅니다.

## 라이선스

MIT — [LICENSE](LICENSE) 참고.
