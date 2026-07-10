"""Console entry point: `jira-dc-mock` — start the mock server via uvicorn."""

from __future__ import annotations

import uvicorn

from .config import load_config
from .server import make_app


def main() -> None:
    config = load_config()
    app = make_app(config=config)
    ro = " (read-only)" if config.readonly else ""
    persist = f"  persist={config.persist}" if config.persist else ""
    print(f"jira-dc-{config.server_version}-mock  http://{config.host}:{config.port}"
          f"  project={config.project_key} locale={config.locale} seed={config.seed}"
          f" latency={config.latency_ms}ms{ro}{persist}")
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
