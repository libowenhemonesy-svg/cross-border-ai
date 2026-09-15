import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gangweiceshi/data_extractors"))
from obsidian_writer import sanitize_filename, write_to_vault


@pytest.mark.parametrize("title", ["", "   ", ".", "..", "...", "\t\n"])
def test_empty_or_dot_title_gets_visible_filename(title):
    name = sanitize_filename(title)
    assert name
    assert not name.startswith(".")
    assert not name.endswith((".", " "))


@pytest.mark.parametrize("title", ["CON", "nul", "COM1", "LPT9", "AUX.txt"])
def test_windows_device_names_are_escaped(title):
    name = sanitize_filename(title)
    assert name.split(".")[0].upper() not in {"CON", "NUL", "COM1", "LPT9", "AUX"}


def test_control_characters_and_trailing_dots_are_removed():
    name = sanitize_filename("运营\x00复盘\n2026. ")
    assert all(ord(char) >= 32 for char in name)
    assert not name.endswith((".", " "))


def test_normal_title_unchanged():
    assert sanitize_filename("亚马逊广告复盘 2026") == "亚马逊广告复盘 2026"


def test_note_with_empty_title_is_saved_as_visible_markdown(tmp_path):
    path = Path(write_to_vault({"summary": "测试摘要", "tags": []}, str(tmp_path), ""))
    assert path.is_file()
    assert not path.name.startswith(".")
    assert path.parent == tmp_path
