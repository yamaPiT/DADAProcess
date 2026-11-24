#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル名：tests/test_dada_verify.py
バージョン番号：1.0.0
作成日：2026-11-24
プログラマ名：DADA Programmer Agent
ファイルの概要：
    統合機械検証CLI（tools/dada_verify.py / UNIT-008）および意味保持検証（style_check.py）・
    既存4CLI後方互換性を検証する単体テストスイート（TC-008, TC-009, TC-012, TC-013, TC-014）。
対応機能ID（トレーサビリティ）：
    UNIT-008 (REQ-003, REQ-004, REQ-008) / TC-008, TC-009, TC-012, TC-013, TC-014
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import agent_def_check  # noqa: E402
import asdoq_lint  # noqa: E402
import dada_check  # noqa: E402
import dada_verify  # noqa: E402
import style_check  # noqa: E402


class TestDadaVerifyUnit008(unittest.TestCase):
    """UNIT-008 統合機械検証CLIと意味保持検証の単体テスト（TC-008, TC-009, TC-012, TC-013, TC-014）。"""

    def test_tc008_style_verify_preserves_meaning_returns_zero(self) -> None:
        """TC-008 (UNIT-008 / REQ-003): ID・数値・単位・否定極性を維持した推敲で終了コード0を検証する。"""
        # Arrange (準備): 一時ディレクトリに元のMarkdown文書と意味スナップショットを作成する
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc_path = root / "sample.md"
            original_text = (
                "# 1. 要求定義\n\n"
                "#### REQ-001: 憲法圧縮\n"
                "- **検証条件**: `.agents/AGENTS.md` は 12,288 bytes 以下とし、無断で実装を開始しない。\n"
            )
            doc_path.write_text(original_text, encoding="utf-8")
            snap_dir = root / "docs" / "process" / ".style_snapshots"

            with mock.patch.object(style_check, "SNAPSHOT_DIR", snap_dir):
                snap_rc = style_check.main(["snapshot", "--input", str(doc_path), "--summary"])
                self.assertEqual(snap_rc, 0)

                # 表現のみ自然化し、REQ-001・12,288 bytes・否定極性（しない）を保持して更新する
                naturalized_text = (
                    "# 1. 要求定義\n\n"
                    "#### REQ-001: 憲法圧縮\n"
                    "- **検証条件**: `.agents/AGENTS.md` の容量は 12,288 bytes 以下に抑え、承認前に実装しない。\n"
                )
                doc_path.write_text(naturalized_text, encoding="utf-8")

                # Act (実行): style_check.py verify および dada_verify.py を実行する
                out_buf = io.StringIO()
                with redirect_stdout(out_buf):
                    verify_rc = style_check.main(["verify", "--input", str(doc_path)])
                dv_buf = io.StringIO()
                with redirect_stdout(dv_buf):
                    dv_rc = dada_verify.main([
                        "--root", str(root),
                        "--input", str(doc_path),
                        "--summary",
                    ])

        # Assert (検証): 意味保持検証が差分異常なし（終了コード0）を返すこと
        self.assertEqual(verify_rc, 0)
        self.assertIn("STYLE-VERIFY: OK", out_buf.getvalue())
        self.assertEqual(dv_rc, 0)
        self.assertIn("DADA-VERIFY: OK", dv_buf.getvalue())

    def test_tc009_style_verify_detects_number_or_negation_loss_returns_one(self) -> None:
        """TC-009 (UNIT-008 / REQ-003): 数値削除と否定極性反転を検出し終了コード1を返すことを検証する。"""
        # Arrange (準備): 数値 12,288 と否定表現を含む文書のスナップショットを保存後、数値を削除・否定反転する
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc_path = root / "broken.md"
            doc_path.write_text(
                "# 1. 仕様\n\n"
                "#### REQ-001: 容量制約\n"
                "- **検証条件**: サイズは 12,288 bytes 以下とし、失敗時は再試行しない。\n",
                encoding="utf-8",
            )
            snap_dir = root / "docs" / "process" / ".style_snapshots"

            with mock.patch.object(style_check, "SNAPSHOT_DIR", snap_dir):
                style_check.main(["snapshot", "--input", str(doc_path)])
                doc_path.write_text(
                    "# 1. 仕様\n\n"
                    "#### REQ-001: 容量制約\n"
                    "- **検証条件**: サイズは規定値以下とし、失敗時は再試行する。\n",
                    encoding="utf-8",
                )

                # Act (実行): verify と dada_verify を実行して変化検出結果を取得する
                out_buf = io.StringIO()
                with redirect_stdout(out_buf):
                    verify_rc = style_check.main(["verify", "--input", str(doc_path)])
                dv_buf = io.StringIO()
                with redirect_stdout(dv_buf):
                    dv_rc = dada_verify.main([
                        "--root", str(root),
                        "--input", str(doc_path),
                        "--summary",
                    ])

        # Assert (検証): 数値消失で終了コード1、否定減少の警告も標準出力へ出力されること
        self.assertEqual(verify_rc, 1)
        output_text = out_buf.getvalue()
        self.assertIn("12,288", output_text)
        self.assertIn("しない", output_text)
        self.assertEqual(dv_rc, 1)
        self.assertIn("DADA-VERIFY: NG", dv_buf.getvalue())

    def test_tc012_1000_lines_under_3s_default_off_and_orthogonal_dedup(self) -> None:
        """TC-012 (UNIT-008 / REQ-004): 1,000行文書の3秒以内処理・既定off・直交重複排除・キャッシュを検証する。"""
        # Arrange (準備): 1,000行規模の開発文書ダミー（曖昧語・指示語・長文を含む）を作成する
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            art_dir = root / "docs" / "artifacts"
            art_dir.mkdir(parents=True, exist_ok=True)
            sw105_path = art_dir / "SW105_ソフトウェア要求仕様書.md"

            long_sentence = (
                "この処理は利用者の入力データを受け取ってから内部の検証処理と変換処理を順番に実行したうえで"
                "出力ディレクトリへ結果を書き出し、さらに後続工程へ通知を行うための一連の長大な処理手順である。"
            )
            lines = [
                "# 1. 概要",
                "読み手は開発者とする。目的は性能検証である。適用範囲は対象内と対象外とする。",
                "",
                "## 2. 機能要求",
                "#### REQ-001: 高速応答",
                "- **概要**: 適切に処理する。上記の手順を用いる。",
                "- **異常系**: エラー時は停止する。",
                "- **検証条件 (Acceptance Criteria)**: 適切に動作すること。",
                "- **優先度**: Must",
                f"- {long_sentence}",
            ]
            for i in range(990):
                lines.append(f"- 項目{i + 1}: 入力値{i + 1}に対して応答コード{i % 5}を返す。")
            sw105_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            # Act (実行): --decision1 省略で1,000行文書を実行し、所要時間・キャッシュHIT/MISSを計測する
            with mock.patch.object(asdoq_lint.RestDecision1Client, "evaluate_decisions") as mock_api:
                out_first = io.StringIO()
                t0 = time.perf_counter()
                with redirect_stdout(out_first):
                    rc1 = dada_verify.main([
                        "--root", str(root),
                        "--phase", "1",
                        "--input", str(sw105_path),
                        "--profile", "sw105",
                    ])
                elapsed1 = time.perf_counter() - t0

                # キャッシュ再利用（未編集 -> HIT、1文字追記 -> MISS）を検証する
                out_hit = io.StringIO()
                with redirect_stdout(out_hit):
                    rc_hit = dada_verify.main([
                        "--root", str(root),
                        "--phase", "1",
                        "--input", str(sw105_path),
                        "--profile", "sw105",
                        "--reuse-cache",
                        "--summary",
                    ])

                with sw105_path.open("a", encoding="utf-8") as fp:
                    fp.write("- 追記行: 追加条件は 10 件以下とする。\n")

                out_miss = io.StringIO()
                with redirect_stdout(out_miss):
                    rc_miss = dada_verify.main([
                        "--root", str(root),
                        "--phase", "1",
                        "--input", str(sw105_path),
                        "--profile", "sw105",
                        "--reuse-cache",
                        "--summary",
                    ])

            report_file = root / "docs" / "process" / "check_report.md"
            cache_file = root / "docs" / "process" / ".verify_cache.json"
            report_exists = report_file.is_file()
            cache_exists = cache_file.is_file()
            report_text = report_file.read_text(encoding="utf-8") if report_exists else ""

            # --no-report 時はレポート出力を抑止することを確認する
            report_file.unlink()
            with redirect_stdout(io.StringIO()):
                dada_verify.main([
                    "--root", str(root),
                    "--phase", "1",
                    "--input", str(sw105_path),
                    "--profile", "sw105",
                    "--no-report",
                    "--summary",
                ])
            report_after_no_report = report_file.exists()

        # Assert (検証): 3.0秒以内・外部API未呼び出し・統合レポート生成・重複統合・キャッシュ動作を確認する
        self.assertLess(elapsed1, 3.0)
        self.assertIn(rc1, (0, 1))
        self.assertEqual(mock_api.call_count, 0)
        self.assertTrue(report_exists)
        self.assertTrue(cache_exists)
        self.assertIn("DADA-VERIFY:", out_first.getvalue())
        self.assertIn("decision1=off", out_first.getvalue())
        self.assertIn("重複統合", report_text)
        self.assertIn("cache=HIT", out_hit.getvalue())
        self.assertEqual(rc_hit, rc1)
        self.assertIn("cache=MISS", out_miss.getvalue())
        self.assertEqual(rc_miss, rc1)
        self.assertFalse(report_after_no_report)

    def test_tc013_existing_four_clis_backward_compatibility(self) -> None:
        """TC-013 (UNIT-008 / REQ-004): 既存4CLIのサブコマンドと終了コード0/1/2の後方互換を検証する。"""
        # Arrange (準備): 既存4CLIの最小正常入力・エラー入力を準備する
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            clean_md = root / "clean.md"
            clean_md.write_text("# 概要\n読み手は開発者とする。目的は確認である。適用範囲は対象内と対象外とする。\n", encoding="utf-8")

            # Act (実行): 既存4CLIの既存インターフェースを呼び出す
            with redirect_stdout(io.StringIO()):
                rc_dada_ok = dada_check.main(["all", "--root", str(root), "--no-report", "--summary"])
            with redirect_stderr(io.StringIO()):
                rc_dada_err = dada_check.main(["all", "--root", str(root / "missing")])

            with redirect_stdout(io.StringIO()):
                rc_asdoq_ok = asdoq_lint.main(["--input", str(clean_md), "--profile", "general", "--summary"])
            with redirect_stderr(io.StringIO()):
                rc_asdoq_err = asdoq_lint.main(["--input", str(root / "missing.md")])

            with redirect_stdout(io.StringIO()):
                rc_style_ok = style_check.main(["lint", "--input", str(clean_md), "--summary"])
            with redirect_stderr(io.StringIO()):
                rc_style_err = style_check.main(["lint", "--input", str(root / "missing.md")])

            with redirect_stdout(io.StringIO()):
                rc_adc_ok = agent_def_check.main(["all", "--root", str(root), "--no-report", "--summary"])
            with redirect_stderr(io.StringIO()):
                rc_adc_err = agent_def_check.main(["all", "--root", str(root / "missing")])

        # Assert (検証): 既存4CLIが変更前と同じ終了コード（正常0・エラー2）を返すこと
        self.assertEqual(rc_dada_ok, 0)
        self.assertEqual(rc_dada_err, 2)
        self.assertEqual(rc_asdoq_ok, 0)
        self.assertEqual(rc_asdoq_err, 2)
        self.assertEqual(rc_style_ok, 0)
        self.assertEqual(rc_style_err, 2)
        self.assertEqual(rc_adc_ok, 0)
        self.assertEqual(rc_adc_err, 2)

    def test_tc014_error_cases_return_exit_code_2_without_network(self) -> None:
        """TC-014 (UNIT-008 / REQ-004): 不在ファイル・不正引数・APIキー未設定--decision1 onで終了コード2を検証する。"""
        # Arrange (準備): 空の一時ルートとテスト用入力ファイルを用意し、GEMINI_API_KEYを除外した環境を作る
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sample = root / "doc.md"
            sample.write_text("# 概要\n本文。\n", encoding="utf-8")

            env_without_key = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
            with mock.patch.dict(os.environ, env_without_key, clear=True):
                with mock.patch("urllib.request.urlopen") as mock_urlopen:
                    # Act (実行): 3種類の異常条件をそれぞれ実行する
                    err_missing = io.StringIO()
                    with redirect_stderr(err_missing):
                        rc_missing = dada_verify.main(["--root", str(root), "--input", str(root / "no_file.md")])

                    err_opt = io.StringIO()
                    with redirect_stderr(err_opt):
                        rc_opt = dada_verify.main(["--root", str(root), "--unknown-flag"])

                    err_key = io.StringIO()
                    with redirect_stderr(err_key):
                        rc_key = dada_verify.main([
                            "--root", str(root),
                            "--input", str(sample),
                            "--decision1", "on",
                        ])

        # Assert (検証): すべて外部通信せず標準エラーへ原因を出力し終了コード2で終了すること
        self.assertEqual(mock_urlopen.call_count, 0)
        self.assertEqual(rc_missing, 2)
        self.assertTrue(len(err_missing.getvalue()) > 0)
        self.assertEqual(rc_opt, 2)
        self.assertTrue(len(err_opt.getvalue()) > 0)
        self.assertEqual(rc_key, 2)
        self.assertIn("GEMINI_API_KEY", err_key.getvalue())


if __name__ == "__main__":
    unittest.main()
