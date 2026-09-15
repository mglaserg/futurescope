from pathlib import Path


def test_app_uses_grouped_top_navigation():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "st.navigation(pages, position=\"top\")" in source
    assert '"Trade": [' in source
    assert '"Research": [' in source
    assert '"Deep Dive": [' in source
    assert "pages/11_Synthetic_Tenors.py" in source


def test_home_explains_three_step_workflow():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "What is unusual right now?" in source
    assert "What exactly is the trade?" in source
    assert "Does the idea actually have edge?" in source
