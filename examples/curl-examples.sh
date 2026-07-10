#!/usr/bin/env bash
# Example requests against a running jira820 (default http://127.0.0.1:8080).
set -euo pipefail
BASE=${BASE:-http://127.0.0.1:8080}
PK=${PK:-DEMO}

echo "# server info"
curl -s "$BASE/rest/api/2/serverInfo" | python -m json.tool

echo "# search (JQL) with field projection + paging"
curl -s "$BASE/rest/api/2/search?jql=project=$PK%20ORDER%20BY%20updated%20DESC&maxResults=3&fields=summary,status,assignee" | python -m json.tool

echo "# one issue with changelog"
curl -s "$BASE/rest/api/2/issue/$PK-1?expand=changelog" | python -m json.tool

echo "# agile: boards (scrum + kanban)"
curl -s "$BASE/rest/agile/1.0/board" | python -m json.tool

echo "# agile: kanban board columns"
curl -s "$BASE/rest/agile/1.0/board/2/configuration" | python -m json.tool

echo "# --- WRITE: create an issue ---"
KEY=$(curl -s -X POST "$BASE/rest/api/2/issue" -H 'Content-Type: application/json' \
  -d "{\"fields\":{\"project\":{\"key\":\"$PK\"},\"issuetype\":{\"name\":\"Task\"},\"summary\":\"created via curl\"}}" \
  | python -c "import sys,json;print(json.load(sys.stdin)['key'])")
echo "created $KEY"

echo "# available transitions, then move to first one"
TID=$(curl -s "$BASE/rest/api/2/issue/$KEY/transitions" | python -c "import sys,json;print(json.load(sys.stdin)['transitions'][0]['id'])")
curl -s -X POST "$BASE/rest/api/2/issue/$KEY/transitions" -H 'Content-Type: application/json' -d "{\"transition\":{\"id\":\"$TID\"}}"
echo "transitioned $KEY via $TID"

echo "# add a comment + worklog"
curl -s -X POST "$BASE/rest/api/2/issue/$KEY/comment" -H 'Content-Type: application/json' -d '{"body":"nice"}' >/dev/null
curl -s -X POST "$BASE/rest/api/2/issue/$KEY/worklog" -H 'Content-Type: application/json' -d '{"timeSpentSeconds":3600}' >/dev/null

echo "# move it into the active sprint (board 1)"
SID=$(curl -s "$BASE/rest/agile/1.0/board/1/sprint?state=active" | python -c "import sys,json;print(json.load(sys.stdin)['values'][0]['id'])")
curl -s -X POST "$BASE/rest/agile/1.0/sprint/$SID/issue" -H 'Content-Type: application/json' -d "{\"issues\":[\"$KEY\"]}"
echo "moved $KEY into sprint $SID"
