from jira_dc_mock import build_store, jql
from jira_dc_mock.config import Config


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
