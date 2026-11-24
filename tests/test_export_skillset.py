#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル名：tests/test_export_skillset.py
バージョン番号：1.0.0
作成日：2026-11-24
プログラマ名：DADA Programmer Agent
ファイルの概要：
    スキルセット切り出しツール（tools/export_skillset.py / UNIT-010）の
    4スキルセット切り出し整合性（リンク切れ0件・agent_def_check通過）および
    切り出し元ファイル欠損時の異常終了を検証する単体テストスイート。
対応機能ID（トレーサビリティ）：
    UNIT-010 (REQ-001, REQ-005) / TC-015, TC-016
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import agent_def_check  # noqa: E402
import export_skillset  # noqa: E402


def _build_valid_export_source(root: Path) -> None:
    """
    関数名：_build_valid_export_source
    戻り値：なし
    引数：root (Path) - テスト用切り出し元リポジトリルート
    関数の概要：4スキルセットすべてが参照リンク切れ0件かつ憲法上限以内で切り出せる最小リポジトリを構築する。
    対応機能ID（トレーサビリティ）：UNIT-010 (TC-015)
    """
    # ワークスペース憲法（12,288B以内・4原則キーワードあり）
    agents_md = root / ".agents" / "AGENTS.md"
    agents_md.parent.mkdir(parents=True, exist_ok=True)
    agents_md.write_text(
        "# DADA 憲法\n"
        "- ドキュメント絶対主義\n- 承認ゲート\n- アテンション\n- 役割の純化\n",
        encoding="utf-8",
    )

    # 全スキルディレクトリに有効な SKILL.md を配置
    all_skill_dirs = [
        "dada-process", "context-reset", "dada-check", "document-writer",
        "requirements-engineer", "requirements-reviewer", "test-engineer", "test-reviewer",
        "architect", "architecture-reviewer", "programmer", "code-reviewer",
        "unit-test-generator", "asdoq-reviewer", "JP-Humanizer", "office-document",
    ]
    for skill in all_skill_dirs:
        sdir = root / ".agents" / "skills" / skill
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: {skill} を実行するためのテスト用スキル定義です。\n---\n\n"
            "## 禁止事項\n- 無断変更を禁止する。\n",
            encoding="utf-8",
        )

    # ツール・ガイドライン・テンプレート・ライセンス類を配置
    file_entries = [
        "tools/dada_check.py",
        "tools/dada_verify.py",
        "tools/dada_benchmark.py",
        "tools/agent_def_check.py",
        "tools/asdoq_lint.py",
        "tools/asdoq_dictionary.json",
        "tools/style_check.py",
        "tools/office_io.py",
        "tools/export_skillset.py",
        "tools/README.md",
        "docs/guidelines/asdoq_writing_rules.md",
        "docs/guidelines/asdoq_checklist.md",
        "docs/guidelines/asdoq_model_markdown.md",
        "docs/guidelines/agent_def_phase_addon.md",
        "docs/guidelines/antigravity_adapter.md",
        "docs/templates/office/README.md",
        "docs/examples/README.md",
        "docs/process/phase5_evaluation_guide.md",
        ".env.example",
        "LICENSE",
        "README.md",
    ]
    for rel_p in file_entries:
        fp = root / rel_p
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text("# dummy\n", encoding="utf-8")


class TestExportSkillsetUnit010(unittest.TestCase):
    """UNIT-010 export_skillset.py の単体テスト（TC-015, TC-016）。"""

    def test_tc015_export_all_four_skillsets_and_verify_integrity(self) -> None:
        """TC-015 (UNIT-010 / REQ-005): dada-core への新ツール追加と4スキルセットすべての整合性を検証する。"""
        # Arrange (準備): 4スキルセットの切り出し元フィクスチャを構築する
        dada_core_paths = export_skillset.SKILLSETS["dada-core"]["paths"]
        self.assertIn("tools/dada_verify.py", dada_core_paths)
        self.assertIn("tools/dada_benchmark.py", dada_core_paths)

        with tempfile.TemporaryDirectory() as tmpdir:
            src_root = Path(tmpdir) / "src"
            _build_valid_export_source(src_root)

            # Act (実行): 4スキルセットすべてを切り出し、切り出し先それぞれに agent_def_check.py を実行する
            for set_name in ("office-suite", "jp-humanizer", "asdoq-reviewer", "dada-core"):
                out_dir = Path(tmpdir) / f"out_{set_name}"
                copied = export_skillset.export_skillset(src_root, set_name, out_dir)
                self.assertTrue(len(copied) > 0)

                adc_buf = io.StringIO()
                with redirect_stdout(adc_buf):
                    rc = agent_def_check.main(["all", "--root", str(out_dir), "--no-report", "--summary"])

                # Assert (検証): 切り出し先でリンク切れ0件・agent_def_check 終了コード0となること
                self.assertEqual(rc, 0, msg=f"{set_name} failed: {adc_buf.getvalue()}")
                if set_name == "dada-core":
                    self.assertTrue((out_dir / "tools" / "dada_verify.py").is_file())
                    self.assertTrue((out_dir / "tools" / "dada_benchmark.py").is_file())
                    self.assertTrue((out_dir / "docs" / "guidelines" / "agent_def_phase_addon.md").is_file())
                    self.assertTrue((out_dir / "docs" / "guidelines" / "antigravity_adapter.md").is_file())

    def test_tc016_missing_source_file_returns_nonzero_exit_code(self) -> None:
        """TC-016 (UNIT-010 / REQ-005): 切り出し元ファイル1件欠損時にエラー表示と終了コード1または2を検証する。"""
        # Arrange (準備): tools/dada_verify.py のみ欠損させた切り出し元フィクスチャを構築する
        with tempfile.TemporaryDirectory() as tmpdir:
            src_root = Path(tmpdir) / "broken_src"
            _build_valid_export_source(src_root)
            (src_root / "tools" / "dada_verify.py").unlink()
            out_dir = Path(tmpdir) / "out_fail"

            # Act (実行): CLI経由および関数経由で切り出しを実行する
            err_buf = io.StringIO()
            with redirect_stderr(err_buf):
                rc_cli = export_skillset.main([
                    "export", "--set", "dada-core", "--out", str(out_dir), "--root", str(src_root)
                ])
            err_arg = io.StringIO()
            with redirect_stderr(err_arg):
                rc_bad_arg = export_skillset.main(["export", "--set", "unknown-set", "--out", str(out_dir)])

        # Assert (検証): 欠損時はエラーメッセージを表示し終了コード1または2を返すこと
        self.assertIn(rc_cli, (1, 2))
        self.assertIn("dada_verify.py", err_buf.getvalue())
        self.assertFalse(out_dir.exists())
        self.assertEqual(rc_bad_arg, 2)


if __name__ == "__main__":
    unittest.main()
