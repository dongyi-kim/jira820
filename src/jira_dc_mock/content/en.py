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
CONF_ACTIONS = ["created", "updated", "commented on"]

SPRINT_GOALS = ["Ship the connector MVP", "Reduce query p95", "Stabilize the pipeline",
                "Close out tech debt", "Onboarding polish", "Harden the API"]
