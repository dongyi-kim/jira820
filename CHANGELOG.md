# 변경 이력

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
