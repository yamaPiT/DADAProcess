#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル名：tests/test_dada_benchmark.py
バージョン番号：1.0.0
作成日：2026-11-24
プログラマ名：DADA Programmer Agent
ファイルの概要：
    ベースライン比較ベンチマークツール（tools/dada_benchmark.py / UNIT-009）の
    正常達成・境界値未達・異常系（欠損パス・不在ルート）を検証する単体テストスイート。
対応機能ID（トレーサビリティ）：
    UNIT-009 (REQ-001, REQ-007) / TC-021, TC-022, TC-023
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import dada_benchmark  # noqa: E402


def _create_benchmark_fixture(
    root: Path,
    agents_bytes: int = 8000,
    phase_file_bytes: int = 2000,
    cli_lines_req_eng: int = 2,
    cli_lines_req_rev: int = 1,
) -> None:
    """
    関数名：_create_benchmark_fixture
    戻り値：なし
    引数：root (Path), agents_bytes (int), phase_file_bytes (int), cli_lines_req_eng (int), cli_lines_req_rev (int)
    関数の概要：全計測対象ファイルを持つ最小ベンチマーク用ダミーリポジトリを構築する。
    対応機能ID（トレーサビリティ）：UNIT-009 (TC-021, TC-022)
    """
    for rel_p in dada_benchmark.collect_required_paths():
        fp = root / rel_p
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(b"a" * phase_file_bytes)

    (root / dada_benchmark.AGENTS_MD_REL).write_bytes(b"x" * agents_bytes)

    eng_cmds = "\n".join(f"`python tools/dada_verify.py --phase 1` # cmd{i}" for i in range(cli_lines_req_eng))
    rev_cmds = "\n".join(f"`python tools/dada_verify.py --reuse-cache` # cmd{i}" for i in range(cli_lines_req_rev))
    (root / ".agents/skills/requirements-engineer/SKILL.md").write_text(
        f"# ReqEng\n{eng_cmds}\n".ljust(phase_file_bytes, " "), encoding="utf-8"
    )
    (root / ".agents/skills/requirements-reviewer/SKILL.md").write_text(
        f"# ReqRev\n{rev_cmds}\n".ljust(phase_file_bytes, " "), encoding="utf-8"
    )


class TestDadaBenchmarkUnit009(unittest.TestCase):
    """UNIT-009 比較ベンチマークツールの単体テスト（TC-021, TC-022, TC-023）。"""

    def test_tc021_passing_workspace_returns_zero_with_table_and_json(self) -> None:
        """TC-021 (UNIT-009 / REQ-007): 目標達成構成で対比表・JSON出力および終了コード0を検証する。"""
        # Arrange (準備): 憲法8,000B・各ファイル2,000B・CLI計3回の目標達成フィクスチャを構築する
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _create_benchmark_fixture(root, agents_bytes=8000, phase_file_bytes=2000, cli_lines_req_eng=2, cli_lines_req_rev=1)

            # Act (実行): markdown / json / summary の3形式でベンチマークを実行する
            md_buf = io.StringIO()
            with redirect_stdout(md_buf):
                rc_md = dada_benchmark.main(["--root", str(root), "--format", "markdown"])

            json_buf = io.StringIO()
            with redirect_stdout(json_buf):
                rc_json = dada_benchmark.main(["--root", str(root), "--format", "json"])

            sum_buf = io.StringIO()
            with redirect_stdout(sum_buf):
                rc_sum = dada_benchmark.main(["--root", str(root), "--summary"])

        # Assert (検証): すべて終了コード0で、7指標対比表とPASSサマリが出力されること
        self.assertEqual(rc_md, 0)
        self.assertIn("DADA-BENCHMARK: PASS", md_buf.getvalue())
        self.assertIn("phase1_prog_write", md_buf.getvalue())
        self.assertEqual(rc_json, 0)
        parsed = json.loads(json_buf.getvalue())
        self.assertTrue(parsed["passed"])
        self.assertEqual(len(parsed["metrics"]), 7)
        self.assertEqual(rc_sum, 0)
        self.assertTrue(sum_buf.getvalue().strip().startswith("DADA-BENCHMARK: PASS"))

    def test_tc022_boundary_failures_return_one_and_identify_failed_metrics(self) -> None:
        """TC-022 (UNIT-009 / REQ-007): 12,289B超過・49.9%削減・CLI 6回の境界未達で終了コード1を検証する。"""
        # Arrange (準備): 3種類の境界未達フィクスチャ（憲法12,289B / 49.9%削減 / CLI 6回）を準備する
        with tempfile.TemporaryDirectory() as tmpdir:
            root_bytes = Path(tmpdir) / "case_bytes"
            _create_benchmark_fixture(root_bytes, agents_bytes=12289, phase_file_bytes=2000)

            root_red = Path(tmpdir) / "case_red"
            _create_benchmark_fixture(root_red, agents_bytes=8000, phase_file_bytes=2000)
            # phase1_prog_write の基準 126,875B に対し 49.9%削減（= 63,564B）となるよう1ファイルを加算する
            # 他ファイル合計: 8000 + 2000*5 = 18000B -> 残り1ファイルを 45564B にすると合計 63564B (削減率 49.90%)
            (root_red / ".agents/skills/document-writer/SKILL.md").write_bytes(b"y" * 45564)

            root_cli = Path(tmpdir) / "case_cli"
            _create_benchmark_fixture(root_cli, agents_bytes=8000, phase_file_bytes=2000, cli_lines_req_eng=4, cli_lines_req_rev=2)

            # Act (実行): 3ケースそれぞれを実行する
            out_bytes = io.StringIO()
            with redirect_stdout(out_bytes):
                rc_bytes = dada_benchmark.main(["--root", str(root_bytes)])

            out_red = io.StringIO()
            with redirect_stdout(out_red):
                rc_red = dada_benchmark.main(["--root", str(root_red)])

            out_cli = io.StringIO()
            with redirect_stdout(out_cli):
                rc_cli = dada_benchmark.main(["--root", str(root_cli), "--summary"])

        # Assert (検証): 全ケースで終了コード1となり、未達項目名と実測値が標準出力へ明示されること
        self.assertEqual(rc_bytes, 1)
        self.assertIn("agents_md_bytes", out_bytes.getvalue())
        self.assertIn("12289", out_bytes.getvalue())

        self.assertEqual(rc_red, 1)
        self.assertIn("phase1_prog_write", out_red.getvalue())
        self.assertIn("49.9%", out_red.getvalue())

        self.assertEqual(rc_cli, 1)
        self.assertIn("cli_checks_per_phase=6", out_cli.getvalue())

    def test_tc023_missing_root_or_required_files_return_two(self) -> None:
        """TC-023 (UNIT-009 / REQ-007): 不在ルートパスおよび必須ファイル欠損で終了コード2を検証する。"""
        # Arrange (準備): 存在しないパスと必須ファイルが欠損したディレクトリを用意する
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_root = Path(tmpdir) / "no_such_dir"
            incomplete_root = Path(tmpdir) / "incomplete"
            incomplete_root.mkdir(parents=True, exist_ok=True)
            (incomplete_root / ".agents").mkdir(parents=True, exist_ok=True)
            (incomplete_root / ".agents" / "AGENTS.md").write_text("# 憲法", encoding="utf-8")

            # Act (実行): 不在ルート・欠損ディレクトリ・不在ベースラインJSONを実行する
            err_missing = io.StringIO()
            with redirect_stderr(err_missing):
                rc_missing = dada_benchmark.main(["--root", str(missing_root)])

            err_inc = io.StringIO()
            with redirect_stderr(err_inc):
                rc_inc = dada_benchmark.main(["--root", str(incomplete_root)])

            err_base = io.StringIO()
            with redirect_stderr(err_base):
                rc_base = dada_benchmark.main(["--root", str(incomplete_root), "--baseline", str(missing_root / "b.json")])

        # Assert (検証): すべて標準エラー出力に原因・欠落パス一覧を表示し終了コード2を返すこと
        self.assertEqual(rc_missing, 2)
        self.assertTrue(len(err_missing.getvalue()) > 0)
        self.assertEqual(rc_inc, 2)
        self.assertIn("requirements-engineer", err_inc.getvalue())
        self.assertEqual(rc_base, 2)
        self.assertTrue(len(err_base.getvalue()) > 0)


if __name__ == "__main__":
    unittest.main()
