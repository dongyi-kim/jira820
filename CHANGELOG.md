# 변경 이력

## 0.10.0

- **Epic Name(단축어) 필드** — `epic_name_field`(기본 `customfield_10011`). Jira 는 Epic 의
  요약과 별개로 보드 칸에 뜨는 짧은 이름을 갖는데, 지금까지 필드 목록에만 있고 값이 없었다.
  이슈 레코드의 `epicName` 을 방출하고 PUT 으로 수정도 된다. **Epic 타입만** 값을 갖는다 —
  다른 타입에 들어 있으면 보드가 오해한다.
- **전이 화면**(`GET /rest/api/2/issue/{key}/transitions?expand=transitions.fields`) + 선택적
  워크플로 스킴(`transition_scheme`) — 전이마다 요구하는 입력(코멘트·담당자·해결책·시간)이 다르다.
- **editmeta 확대** — priority·reporter·components·Epic Link 에 `allowedValues` 를 실어,
  소비자가 "지금 이 사용자가 무엇을 고칠 수 있는가" 를 추측 없이 알 수 있다.
- **JQL 값 자동완성** `GET /rest/api/2/jql/autocompletedata/suggestions` (라벨 등).
- `GET /rest/api/2/configuration` — timeTrackingConfiguration(1일 = 몇 시간 등).
- **첨부 링크 `[^file.pdf]` 렌더** — 실 Jira 처럼 첨부 URL 로 해석한다.
- JQL: 괄호 그룹 `(a OR b) AND c`, `!=`/`NOT IN`, 스프린트 함수(`openSprints()` 등).
- 이슈 링크·원격 링크(Confluence/웹) 생성·삭제.
- 렌더: 코드블록을 실 Jira 태그(`pre.jecodeblock > code.language-X`)로, 강제개행 `\` → `<br/>`,
  `!첨부파일!` 을 첨부 URL 로, 표 셀 파이프 이스케이프.
- 시각: 댓글에 실제 현재 시각 부여(고정 09:00 이라 정렬이 뒤섞였다), `HH:MM:SS` 지원.
- `GET /rest/api/2/user/search` (멘션 자동완성용).

## 0.9.0

- **검색 excerpt 를 검색어 주변 스니펫으로** — CQL 의 text/siteSearch/title ~ "term" 에서
  검색어를 뽑아, 매칭 부분을 중심으로 잘라 하이라이트 마커(@@@hl@@@…@@@endhl@@@)로 감싼다.
  이전에는 본문 앞 180자를 그대로 줬다. 검색어가 본문에 없으면 앞부분 폴백.

## 0.8.0

- **Confluence 검색 결과에 문서 경로** — content 에 `ancestors`(상위 폴더 [최상위 … 직계부모])와
  `space.name`(표시 이름)을 방출한다. 페이지 레코드의 `ancestors`(폴더 제목 리스트)·`spaceName`
  을 부풀린다. 소비자가 breadcrumb(문서 경로)를 그릴 수 있다.

## 0.7.0

- **이슈 remote link(Confluence/Web) 지원** — `GET /rest/api/2/issue/{key}/remotelink`.
  실 Jira DC 형태 `[{id, object:{url, title, icon?}, application?, relationship?}]`.
  이슈 레코드의 `remotelinks: [{url, title, icon?, application?, relationship?}]` 를 방출한다.
  샘플 world 가 일부 이슈에 Confluence 문서 + 외부 Web link 를 붙여 둔다.
  (Jira 링크는 티켓뿐 아니라 Confluence·Web 도 가리킨다 — 소비자가 '관련 문서'로 합칠 수 있게.)
- **우선순위(priority) 를 일반화** — 이전에는 모든 이슈가 `Medium` 으로 고정이었습니다.
  - 이슈가 자기 `priority` 를 가질 수 있습니다(`Store` 의 이슈 레코드 `priority` 필드).
  - 우선순위 목록을 설정으로 갈아끼웁니다: `priorities: [[name, id], ...]`.
    기본값은 Jira DC 기본 스킴(Highest/High/Medium/Low/Lowest).
  - `default_priority` — 이슈에 값이 없을 때 붙일 기본값. 지정하지 않으면 목록의 가운데.
    "값 없음이 아니라 항상 기본값이 붙는" 운용(예: `Unclassified`)을 표현할 수 있습니다.
  - `GET /rest/api/2/priority` 가 설정된 목록을 반환합니다(고정 1건 → 목록).
  - 목록에 없는 이름도 그대로 통과시킵니다(`id: "0"`) — mock 이 스킴을 판단하지 않습니다.

## 0.6.0

- **이슈 링크(issuelinks)** — 실 Jira DC 형태로 `fields.issuelinks` 를 제공합니다.
  `{id, type:{id,name,inward,outward}, inwardIssue|outwardIssue:{key,fields:{summary,status,issuetype}}}`.
  링크 타입: `Relates`(relates to) · `Blocks`(blocks / is blocked by) ·
  `Duplicate`(duplicates / is duplicated by) · `Cloners`(clones / is cloned by).
  샘플 world 가 몇 쌍을 **양방향**(한쪽 outward / 상대 inward)으로 연결해 둡니다.
- `GET /rest/api/2/issueLinkType` — 링크 타입 목록 엔드포인트 추가.
- 링크가 없는 이슈도 `issuelinks: []` 로 필드 자체는 존재합니다(실 Jira 동작과 동일).

## 0.5.0

- **통합 검색 기반**:
  - JQL `text ~ "..."` (요약+설명+코멘트 전문검색), `description ~` / `comment ~` 추가.
  - **Confluence 검색** — 연동 Confluence DC(기본 9.2.4) 형태의 CQL 검색.
    `GET /rest/api/search`(excerpt 스니펫 포함)·`GET /rest/api/content/search` 가 CQL
    `space in (...)` · `title ~` · `text ~`/`siteSearch ~` · `contributor=` · `lastmodified >= now("-14d")`
    를 페이지 코퍼스에서 검색(`cql.py`). 결과 URL 은 9.x 형태 `/spaces/{space}/pages/{id}/{title}`.
  - 페이지에 `body` 부여(text 검색용). `store.confluence_pages()` 코퍼스 헬퍼.
- **멀티 프로젝트**: 이슈별 `project` 로 직렬화(`project_ref`) → 여러 프로젝트를 한 스토어에 담아
  `project = X` / `project in (A, B)` 검색 가능. 소비자가 자체 프로젝트/스페이스를 **additive 주입**
  (`store.issues.update(...)`)해 멀티 프로젝트/스페이스 시나리오를 테스트할 수 있다.
- 기본 샘플 프로젝트명 `DEMO` → **`JIRA820`**. `confluence_version`(기본 9.2.4) 설정 추가.
- JQL/CQL 공용 `_split_and` 의 `in (...)` 닫는 괄호 오제거 버그 수정.

## 0.4.0

- **renderedFields / renderedBody (위키→HTML 서버 렌더)**: `GET issue/{key}?expand=renderedFields` 응답에
  `renderedFields.description`(HTML), 코멘트에 `renderedBody`(HTML) 제공 — 실 Jira DC 8.20.8 처럼 서버가 렌더.
  지원: heading(`hN.`)·bold/italic·monospace(`{{..}}`)·code(`{code}`/`{noformat}`)·blockquote(`{quote}`/`bq.`)·
  panel(`{panel}`)·callout(`{note}`/`{info}`/`{warning}`/`{tip}`)·table(`||h||`/`|c|`)·list(`*`,`#`)·
  image(`!url!`)·link(`[t|url]`)·mention(`[~user]`).
- 맨션은 실 Jira 형태 `<a class="user-hover" href="/secure/ViewProfile.jspa?name=..">표시명</a>` 로 렌더
  (username→displayName 해석). 새 모듈 `jira820/render.py`.

## 0.3.0

- **데모 웹 UI** 추가(`demo/index.html`, 단일 파일 바닐라 JS). 서버가 `/demo` 에서 서빙하고 `/` → `/demo/`
  리다이렉트. 티켓 보기·검색·생성·속성 수정·전이·코멘트·파일/이미지 업로드 지원. (wheel 에 포함)

## 0.2.0

- **첨부파일/이미지 지원**: 이슈에 파일 업로드(멀티파트)·다운로드·목록(`fields.attachment`)·삭제.
  설명/코멘트 body 에 위키 마크업(`!image.png!`, `[^file.pdf]`)으로 참조하는 실제 Jira 흐름 지원.
  엔드포인트: `POST issue/{key}/attachments`, `GET/DELETE attachment/{id}`,
  `GET /secure/attachment/{id}/{filename}`(+`/secure/thumbnail/...`). 파일 영속화(base64).
- 의존성에 `python-multipart` 추가.

## 0.1.0

첫 릴리스.

- Jira Data Center 8.20.8 의 상태형 mock: REST v2(읽기+쓰기)와 Agile `/rest/agile/1.0/`.
- 결정적 시드 데이터셋(사용자, Epic → Story/Task/Bug → Sub-task, 코멘트, 워크로그, 버전, activity ATOM,
  Confluence 페이지). `JIRA820_*` 환경변수 + YAML 로 설정.
- 쓰기: 이슈 생성/수정/삭제, 전이(resolution + changelog), 코멘트, 워크로그, 담당자.
- Agile: 시드된 Scrum 보드 + 스프린트(closed/active/future), Kanban 보드 + 컬럼; 스프린트/백로그 이동,
  스프린트 생성/시작; 칸반 컬럼 이동 = 전이.
- 확장 JQL, 파일 영속화(`JIRA820_PERSIST`), 읽기전용 모드(`JIRA820_READONLY`), 영어/한국어 로케일.
- 외부 데이터 주입 훅(`Store(config, seed=False)`, `config.subtask_type`) — 다른 프로젝트의 world 를 주입해
  이 패키지의 서버로 서빙 가능.
