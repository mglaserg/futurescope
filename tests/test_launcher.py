from pathlib import Path

from futurescope.launcher import build_streamlit_command


def test_launcher_uses_active_python_and_app_path(tmp_path):
    command = build_streamlit_command(tmp_path, port=8502, address="127.0.0.1")
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[4] == str(Path(tmp_path).resolve() / "app.py")
    assert command[-4:] == ["--server.port", "8502", "--server.address", "127.0.0.1"]
