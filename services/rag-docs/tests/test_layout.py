"""폴더 뼈대 확인. 기능 시험은 스크립트마다 따로 둔다."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_and_requirements_exist():
    assert (ROOT / "README.md").is_file()
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8").split()
    assert {"boto3", "pypdf", "pyyaml"} <= set(reqs)


def test_pdfs_are_ignored():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    assert "*.pdf" in ignored
