"""jira820: a stateful, read+write mock of Jira Data Center 8.20.8.

Public API:
    make_app(store=None, config=None) -> FastAPI     # build the ASGI app
    build_store(config=None) -> Store                # build/seed a data store
    load_config() -> Config                          # read JIRA820_* env + YAML
"""

from .config import Config, load_config
from .server import build_store, make_app
from .store import JiraError, Store

__version__ = "0.8.0"
__all__ = ["make_app", "build_store", "load_config", "Config", "Store", "JiraError", "__version__"]
