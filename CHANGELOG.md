# Changelog

## 0.1.0

Initial release.

- Stateful mock of Jira Data Center 8.20.8: REST v2 (read + write) and Agile `/rest/agile/1.0/`.
- Deterministic seeded dataset (users, Epic → Story/Task/Bug → Sub-task, comments, worklogs,
  versions, activity ATOM, Confluence pages), configurable via `JIRAMOCK_*` env + YAML.
- Write endpoints: create/edit/delete issues, transitions (with resolution + changelog),
  comments, worklogs, assignee.
- Agile: seeded Scrum board with sprints (closed/active/future) + Kanban board with columns;
  sprint/backlog moves, create/start sprint; kanban column move == transition.
- Extended JQL, optional file persistence (`JIRAMOCK_PERSIST`), read-only mode (`JIRAMOCK_READONLY`),
  English/Korean locales.
