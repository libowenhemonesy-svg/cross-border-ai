import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gangweiceshi/data_extractors"))
import obsidian_writer


def test_failed_replace_keeps_previous_note(tmp_path, monkeypatch):
    note = tmp_path / "复盘.md"
    note.write_text("原始内容", encoding="utf-8")
    monkeypatch.setattr(obsidian_writer.os, "replace", Mock(side_effect=OSError("disk-error")))
    with pytest.raises(OSError):
        obsidian_writer.write_to_vault({"summary": "新摘要"}, str(tmp_path), "复盘")
    assert note.read_text(encoding="utf-8") == "原始内容"
    assert list(tmp_path.iterdir()) == [note]


def test_successful_save_replaces_complete_note(tmp_path):
    note = tmp_path / "复盘.md"
    note.write_text("原始内容", encoding="utf-8")
    result = obsidian_writer.write_to_vault({"summary": "新摘要", "full_text": "新原文"}, str(tmp_path), "复盘")
    assert Path(result) == note
    assert "新摘要" in note.read_text(encoding="utf-8")
    assert "新原文" in note.read_text(encoding="utf-8")
    assert list(tmp_path.iterdir()) == [note]


def test_flush_failure_keeps_previous_note(tmp_path, monkeypatch):
    note = tmp_path / "复盘.md"
    note.write_text("原始内容", encoding="utf-8")
    monkeypatch.setattr(obsidian_writer.os, "fsync", Mock(side_effect=OSError("disk-full")))
    with pytest.raises(OSError):
        obsidian_writer.write_to_vault({"summary": "新摘要"}, str(tmp_path), "复盘")
    assert note.read_text(encoding="utf-8") == "原始内容"
    assert list(tmp_path.iterdir()) == [note]
