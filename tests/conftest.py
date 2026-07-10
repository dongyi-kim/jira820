import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from fastapi.testclient import TestClient

from jira_dc_mock import make_app
from jira_dc_mock.config import Config


@pytest.fixture
def app():
    return make_app(config=Config(seed="test"))


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def pk(app):
    return app.state.store.config.project_key


def ok(r):
    assert r.status_code < 300, (r.status_code, r.text[:300])
    return r.json() if r.content else None
