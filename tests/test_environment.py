import os

from futurescope.environment import load_futurescope_env


def test_load_futurescope_env_reads_repo_root_env(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    monkeypatch.delenv("GOLDPRICE_API_KEY", raising=False)
    (tmp_path / ".env").write_text("DATABENTO_API_KEY=db-test-from-dotenv\n")

    status = load_futurescope_env(tmp_path)

    assert status.env_file_exists is True
    assert status.databento_configured is True
    assert os.environ["DATABENTO_API_KEY"] == "db-test-from-dotenv"


def test_load_futurescope_env_reports_missing_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)

    status = load_futurescope_env(tmp_path)

    assert status.env_file_exists is False
    assert status.databento_configured is False
