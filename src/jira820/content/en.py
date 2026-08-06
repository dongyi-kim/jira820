"""English (default) content pools. Business-neutral, generic software domain."""

# Personal name pools (fictional). Companies are classic placeholder names.
FIRST_NAMES = [
    "Alex", "Sam", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie",
    "Avery", "Quinn", "Drew", "Reese", "Cameron", "Skyler", "Devon", "Harper",
    "Rowan", "Emerson", "Finley", "Sawyer",
]
LAST_NAMES = [
    "Smith", "Johnson", "Lee", "Brown", "Garcia", "Miller", "Davis", "Wilson",
    "Martin", "Nguyen", "Clark", "Lewis", "Walker", "Hall", "Young", "Patel",
    "Kim", "Chen", "Rossi", "Novak",
]
COMPANIES = ["Acme", "Acme", "Acme", "Globex", "Initech", "Umbrella"]

ROLES = ["Engineer", "Analyst", "Platform Ops", "QA", "Designer", "Tech Lead"]

SUMMARY = {
    "Epic": ["Stabilize realtime pipeline", "Standardize metadata", "Optimize bulk ingestion", "Improve query latency"],
    "Story": ["Add new connector", "Dashboard widget", "Finalize API spec", "Apply caching strategy"],
    "Task": ["Set up environment", "Improve deploy pipeline", "Add data quality rule", "Schema migration"],
    "Bug": ["Fix NPE", "Fix boundary error", "Resolve concurrency issue", "Adjust timeout"],
    "Improvement": ["Improve log format", "Query tuning", "Harden retry policy", "Better error messages"],
    "New Feature": ["Incremental CDC support", "Rollback API", "Realtime alerts", "Self-service lookup"],
    "Sub-task": ["Unit tests", "Address code review", "QA verification", "Release notes"],
}

DESCRIPTION = {
    "Bug": "Reproduced on [env] staging. Steps: {steps}. Expected vs actual differ; needs a root-cause fix.",
    "Story": "As a {role}, I want {goal} so that {benefit}.\nAcceptance criteria:\n- {ac1}\n- {ac2}",
    "Task": "Work item: {item}. Deliverable checked into the repo with a short note.",
    "_default": "Tracking item for {module}. See linked work for details.",
}
STORY_GOALS = ["a faster export", "incremental sync", "clearer errors", "a rollback path", "self-service access"]
BENEFITS = ["I can ship sooner", "operations are simpler", "fewer support tickets", "the team is unblocked"]
ACS = ["covered by tests", "documented", "reviewed", "measured before/after", "no regression"]
BUG_STEPS = ["submit a large batch", "toggle the feature flag twice", "replay yesterday's events", "run under load"]
TASK_ITEMS = ["environment config", "deploy pipeline tweak", "add a data-quality rule", "schema migration"]

# comment kind + template ({a}=author name, {m}=a module, {who}=a person)
COMMENT_TYPES = [
    ("standup", "Standup: made progress on this, continuing today."),
    ("blocker", "Blocked on {m} — waiting for a review from {who}."),
    ("question", "Quick question: should this also cover the {m} path?"),
    ("review", "Reviewed the change, left a couple of minor comments."),
    ("qa", "QA passed on staging, ready for release."),
    ("decision", "Decision: we'll go with the simpler approach for now."),
    ("mention", "cc {who} — please take a look when you get a chance."),
    ("dependency", "Depends on the {m} work landing first."),
    ("transition", "Moving this forward now that the blocker is cleared."),
]

CONF_TITLES = ["ADR: caching strategy", "Sprint retro notes", "Runbook: incident response",
               "Design doc: connector v2", "Onboarding guide", "API contract review"]
CONF_SPACES = ["ENG", "PMO", "ARCH", "OPS"]
CONF_SPACE_NAMES = {"ENG": "Engineering", "PMO": "PMO", "ARCH": "Architecture", "OPS": "Operations"}
# Bitbucket 저장소/코드 시드 풀
REPO_NAMES = ["data-pipeline", "catalog-service", "query-engine", "auth-gateway", "monitoring-agent", "web-console"]
CODE_SAMPLES = [
    ("src/main/java/App.java", ["public class App {", "    void run() { log.info(\"start\"); }", "}"]),
    ("README.md", ["# Service", "Deployment and ops guide.", "See config.yml for settings."]),
    ("src/config.py", ["DEBUG = False", "TIMEOUT = 30", "def load(): return {}"]),
    ("pipeline/etl.py", ["def transform(df):", "    return df.dropna()", ""]),
]
# 상위 폴더 경로 후보(0~3단) — [top … immediate parent]
CONF_FOLDERS = {
    "ENG": [[], ["Pipelines"], ["Pipelines", "Streaming"], ["Standards"], ["Standards", "Data Governance"]],
    "PMO": [[], ["Reports"], ["Reports", "Weekly"], ["Deliverables"]],
    "ARCH": [[], ["Design"], ["Design", "Decisions"], ["Design", "Reviews"]],
    "OPS": [[], ["Runbooks"], ["Runbooks", "Incidents"], ["Runbooks", "Incidents", "Postmortems"], ["Monitoring"]],
}
CONF_ACTIONS = ["created", "updated", "commented on"]

# Remote link / cross-reference wording
WEB_LINK_TITLE = "Deploy runbook (Web)"
CONF_RELATED_LABEL = "Related tickets"
CROSSREF_COMMENT = "Prior context lives in {key} — worth a read before starting."

# Per-document-type bodies — **index-aligned with CONF_TITLES**.
# Previously the body was a single "Title. Other title" line: CQL full-text search worked,
# but there was nothing to actually read or summarize. Multi-section bodies fix that.
CONF_BODIES = [
    # 0) ADR: caching strategy
    """Status: Accepted

Context
Read latency in the {module} module has grown, and the same queries are issued repeatedly.
p95 exceeds the target two or three times a day.

Decision
Introduce a per-read cache with a TTL of {ttl} seconds. Invalidation happens only via an explicit refresh path.

Rationale
- Re-reading everything is expensive and the data changes rarely
- {benefit}

Consequences
- On a cache miss the first response is as slow as before
- Screens that need strong consistency must refresh first

Follow-up
- {ac}""",
    # 1) Sprint retro notes
    """Attendees: {who} and the team

Keep
- Work around {goal} landed on schedule
- Review turnaround got noticeably shorter

Problem
- {item} took longer than expected
- Two issues were found right before the release

Try
- {ac}
- Agree on acceptance criteria before starting

Action items
- {who} to write this up before the next sprint starts""",
    # 2) Runbook: incident response
    """Applies to: {module}

Symptoms
- The ingestion lag alert stays firing for more than 10 minutes
- Dashboard numbers stop updating

First checks
1. Review recent deployments
2. Look at queue backlog and consumer health
3. Check whether the source system announced maintenance

Procedure
1. Restart the consumers
2. Move failed records to the retry queue
3. Escalate to {who} if it does not recover within 10 minutes

Afterwards
- Write a postmortem and file prevention items as tickets""",
    # 3) Design doc: connector v2
    """Background
The current connector only supports full loads, so the nightly window for {module} keeps growing.

Goals
- {goal}
- Checkpoints so a run can resume from the failure point

Scope
- In: incremental extraction, schema-change detection, retry policy
- Out: source system schema changes, UI rework

Design
Split into extract -> normalize -> load, and make each stage idempotent.
Checkpoints are stored per batch; a restart resumes from the last successful point.

Risks and mitigations
- Missed schema change -> add a pre-flight validation stage
- Duplicate loads -> upsert on the business key

Verification
- {ac}""",
    # 4) Onboarding guide
    """For: new joiners on {module}

First week
1. Request access (repositories, dashboards, monitoring)
2. Set up a local environment and run one sample pipeline end to end
3. Read the latest retro and the runbook

Rules to know
- Every piece of work gets a ticket, linked to its parent
- Completion is recorded by transitioning status, nothing else
- Never leave the assignee empty

FAQ
- Where do I start? -> {item} gives you the whole flow

Mentor: {who}""",
    # 5) API contract review
    """Under review: the {module} read API

Agreed
- Responses are paginated by default
- Error responses separate code from message
- Breaking changes require a version bump

Open questions
- Default sort order for bulk reads
- Whether {item} related fields are required

Conclusion
Prioritize {goal}; open questions are settled at the next review.

Attendees: {who}""",
]

SPRINT_GOALS = ["Ship the connector MVP", "Reduce query p95", "Stabilize the pipeline",
                "Close out tech debt", "Onboarding polish", "Harden the API"]
