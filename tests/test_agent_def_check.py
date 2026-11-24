#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル名：tests/test_agent_def_check.py
バージョン番号：1.0.0
作成日：2026-11-24
プログラマ名：DADA Programmer Agent
ファイルの概要：
    エージェント定義チェッカ（tools/agent_def_check.py / UNIT-010）の
    ワークスペース憲法12,288 bytes上限検査・必須4原則キーワード検査・
    キャッシュパス除外（.verify_cache.json, benchmark_report.md）を検証する単体テストスイート。
対応機能ID（トレーサビリティ）：
    UNIT-010 (REQ-001, REQ-005) / TC-001, TC-002
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import agent_def_check  # noqa: E402


def _make_base_agents_root(root: Path, agents_content: str | bytes, ref_exists: bool = True) -> None:
    """
    関数名：_make_base_agents_root
    戻り値：なし
    引数：root (Path), agents_content (str | bytes), ref_exists (bool)
    関数の概要：AGENTS.md とテスト用 SKILL.md を持つ最小エージェント定義ルートを構築する。
    対応機能ID（トレーサビリティ）：UNIT-010 (TC-001, TC-002)
    """
    agents_dir = root / ".agents"
    skill_dir = agents_dir / "skills" / "sample-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(agents_content, bytes):
        (agents_dir / "AGENTS.md").write_bytes(agents_content)
    else:
        (agents_dir / "AGENTS.md").write_text(agents_content, encoding="utf-8")

    ref_file = root / "docs" / "guidelines" / "ref.md"
    ref_file.parent.mkdir(parents=True, exist_ok=True)
    if ref_exists:
        ref_file.write_text("# ref\n", encoding="utf-8")

    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: sample-skill\n"
        "description: テスト用のサンプルスキル定義ファイルです。\n"
        "---\n\n"
        "参照: `docs/guidelines/ref.md`\n"
        "出力先キャッシュ: `docs/process/.verify_cache.json` / `docs/process/benchmark_report.md`\n\n"
        "## 禁止事項\n- 禁止事項テスト。\n",
        encoding="utf-8",
    )


class TestAgentDefCheckUnit010(unittest.TestCase):
    """UNIT-010 agent_def_check.py 拡張検証の単体テスト（TC-001, TC-002）。"""

    def test_tc001_valid_agents_md_at_12288_bytes_boundary_returns_zero(self) -> None:
        """TC-001 (UNIT-010 / REQ-001): 12,288 bytes境界内憲法・4原則完備・キャッシュ除外で終了コード0を検証する。"""
        # Arrange (準備): 4原則を含み厳密に UTF-8 12,288 bytes の .agents/AGENTS.md を構築する
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            header = (
                "# 憲法\n"
                "- ドキュメント絶対主義\n"
                "- 承認ゲート\n"
                "- アテンション-リセット\n"
                "- 役割の純化\n"
            )
            header_bytes = header.encode("utf-8")
            padded = header_bytes + b"a" * (12288 - len(header_bytes))
            _make_base_agents_root(root, padded, ref_exists=True)
            self.assertEqual((root / ".agents" / "AGENTS.md").stat().st_size, 12288)

            # Act (実行): agent_def_check.py skill を実行する
            out_buf = io.StringIO()
            with redirect_stdout(out_buf):
                rc = agent_def_check.main(["skill", "--root", str(root), "--no-report"])

        # Assert (検証): 12,288 bytesちょうどかつ生成物キャッシュパス無視により終了コード0を返すこと
        self.assertEqual(rc, 0, msg=out_buf.getvalue())
        self.assertIn("High 0", out_buf.getvalue())

    def test_tc002_exceeded_12289_bytes_missing_principle_or_dead_link_returns_one(self) -> None:
        """TC-002 (UNIT-010 / REQ-001): 12,289B超過・4原則欠落・参照欠損で終了コード1を検証する。"""
        # Arrange (準備): (1) 12,289 bytes超過、(2) 原則欠落、(3) 参照先欠損 の3パターンを準備する
        with tempfile.TemporaryDirectory() as tmpdir:
            root_over = Path(tmpdir) / "over"
            base = (
                "# 憲法\n"
                "- ドキュメント絶対主義\n"
                "- 承認ゲート\n"
                "- アテンション-リセット\n"
                "- 役割の純化\n"
            )
            base_bytes = base.encode("utf-8")
            over_bytes = base_bytes + b"a" * (12289 - len(base_bytes))
            _make_base_agents_root(root_over, over_bytes, ref_exists=True)

            root_missing_kw = Path(tmpdir) / "missing_kw"
            _make_base_agents_root(
                root_missing_kw,
                "# 憲法\n- ドキュメント絶対主義\n- 承認ゲート\n- アテンション\n",  # 役割の純化が欠落
                ref_exists=True,
            )

            root_dead_ref = Path(tmpdir) / "dead_ref"
            _make_base_agents_root(
                root_dead_ref,
                base,
                ref_exists=False,  # docs/guidelines/ref.md が不在
            )

            # Act (実行): それぞれに対して agent_def_check.py skill を実行する
            out_over = io.StringIO()
            with redirect_stdout(out_over):
                rc_over = agent_def_check.main(["skill", "--root", str(root_over), "--no-report"])

            out_kw = io.StringIO()
            with redirect_stdout(out_kw):
                rc_kw = agent_def_check.main(["skill", "--root", str(root_missing_kw), "--no-report"])

            out_ref = io.StringIO()
            with redirect_stdout(out_ref):
                rc_ref = agent_def_check.main(["skill", "--root", str(root_dead_ref), "--no-report"])

        # Assert (検証): すべて High 指摘が検出され終了コード1を返すこと
        self.assertEqual(rc_over, 1)
        self.assertIn("12289", out_over.getvalue())
        self.assertEqual(rc_kw, 1)
        self.assertIn("役割の純化", out_kw.getvalue())
        self.assertEqual(rc_ref, 1)
        self.assertIn("docs/guidelines/ref.md", out_ref.getvalue())


if __name__ == "__main__":
    unittest.main()
