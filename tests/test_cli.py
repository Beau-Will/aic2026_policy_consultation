"""CLI 测试（本地命令，不需要 API Key）。"""

from __future__ import annotations

import json

from policy_agent.cli import main


def test_cli_import_search_stats(tmp_path, capsys, sample_md):
    db = tmp_path / "cli.db"

    assert main(["--db", str(db), "import", str(sample_md)]) == 0
    import_out = capsys.readouterr().out
    assert "完成" in import_out and "4 条条文" in import_out

    assert main(["--db", str(db), "search", "申报时间", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] >= 1
    assert any(hit["article_no"] == "第四条" for hit in payload["hits"])

    assert main(["--db", str(db), "stats"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats == {"documents": 1, "articles": 4}


def test_cli_search_without_hit_returns_nonzero(tmp_path, capsys):
    db = tmp_path / "empty.db"
    assert main(["--db", str(db), "search", "完全不相关的内容"]) != 0


def test_cli_validate_offline(capsys):
    assert main(["validate"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is True
    assert len(report["skills"]) == 4


def test_cli_preflight_ok(capsys):
    assert main(["preflight"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
