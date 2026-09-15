import pytest

pytest.importorskip("fastapi")

from futurescope.api import create_app


def test_api_routes_exist():
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/health" in paths
    assert "/api/today/{market}" in paths
    assert "/api/data/status" in paths
    assert "/api/data/backfill" in paths
    assert "/api/research/mean-reversion" in paths
