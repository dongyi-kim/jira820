from jira820 import build_store, jql
from jira820.config import Config


def _store():
    return build_store(Config(seed="test"))


def test_base_four_shapes():
    s = _store()
    pk = s.config.project_key
    # 1) epic link
    epic = next(k for k, it in s.issues.items() if it["type"] == "Epic" and s.epic_children.get(k))
    kids = jql.filter_keys(s, f'"Epic Link" = {epic}')
    assert kids and all(s.issues[k]["epicKey"] == epic for k in kids)
    # 2) project + labels + order by updated desc
    r = jql.filter_keys(s, f'project={pk} ORDER BY updated DESC')
    updates = [s.issues[k]["updated"] for k in r]
    assert updates == sorted(updates, reverse=True)
    # 3) assignee + statusCategory In Progress
    a = next(it["assignee"] for it in s.issues.values() if it.get("assignee"))
    r = jql.filter_keys(s, f'assignee = "{a}" AND statusCategory = "In Progress"')
    assert all(s.issues[k]["assignee"] == a and s.issues[k]["statusCategory"] == "inprogress" for k in r)
    # 4) assignee + done + resolved >= -7d
    r = jql.filter_keys(s, f'assignee = "{a}" AND statusCategory = Done AND resolved >= -7d')
    assert all(s.issues[k]["statusCategory"] == "done" for k in r)


def test_default_order_is_key_ascending():
    s = _store()
    r = jql.filter_keys(s, f'project={s.config.project_key}')
    assert r == sorted(r)


def test_in_or_type_sprint():
    s = _store()
    pk = s.config.project_key
    bugs_stories = jql.filter_keys(s, f'project={pk} AND type IN (Bug, Story)')
    assert all(s.issues[k]["type"] in ("Bug", "Story") for k in bugs_stories)
    # OR
    r = jql.filter_keys(s, 'type = Bug OR type = Epic')
    assert all(s.issues[k]["type"] in ("Bug", "Epic") for k in r)
    # sprint filter by state
    active = jql.filter_keys(s, 'sprint = active')
    for k in active:
        assert any(s.sprints[sid]["state"] == "active" for sid in s.issues[k]["sprints"])


def test_status_name_filter():
    s = _store()
    name = s.config.statuses[0][0]
    r = jql.filter_keys(s, f'status = "{name}"')
    assert all(s.issues[k]["statusName"] == name for k in r)


def test_negation_operators_invert_the_match():
    """!= / NOT IN 은 뒤집혀야 한다. (전엔 op 를 무시해 '완료만' 같은 정반대 결과가 나왔다.)"""
    from jira820 import make_app
    from fastapi.testclient import TestClient
    cl = TestClient(make_app())

    def cats(jql):
        r = cl.get("/rest/api/2/search",
                   params={"jql": jql, "fields": "status", "maxResults": 500}).json()
        return {i["fields"]["status"]["statusCategory"]["key"] for i in r["issues"]}

    assert cats("project = JIRA820 AND statusCategory = Done") == {"done"}
    assert "done" not in cats("project = JIRA820 AND statusCategory != Done")
    assert cats("project = JIRA820 AND statusCategory != Done")      # 비어 있으면 검증이 무의미
    assert "Epic" not in {t for t in cats("project = JIRA820 AND type NOT IN (Epic)")}


def test_parentheses_group_or_against_and():
    """'(a OR b) AND c' — 괄호를 무시하고 자르면 조건이 통째로 무너진다(전에 그랬다)."""
    from jira820 import make_app
    from fastapi.testclient import TestClient
    cl = TestClient(make_app())

    def keys(jql):
        r = cl.get("/rest/api/2/search",
                   params={"jql": jql, "fields": "status", "maxResults": 999}).json()
        return {i["key"] for i in r["issues"]}

    all_open = keys('project = JIRA820 AND statusCategory != Done')
    grouped = keys('(project = JIRA820 OR project = NOPE) AND statusCategory != Done')
    assert grouped == all_open and grouped                 # 괄호가 OR 를 묶어야 같은 결과
    # 괄호가 없으면 AND 가 더 강하게 묶인다(Jira 우선순위) → 결과가 달라야 정상
    assert keys('project = NOPE OR project = JIRA820 AND statusCategory = Done') \
        == keys('project = JIRA820 AND statusCategory = Done')
