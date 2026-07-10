# 변경 이력

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
