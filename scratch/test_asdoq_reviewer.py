#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル名：tests/test_asdoq_reviewer.py
バージョン番号：1.2.0
作成日：2026-11-13
プログラマ名：DADA Programmer Agent
ファイルの概要：
    asdoq-reviewer（UNIT-001〜UNIT-007）の自動テストスイート（TC-001〜TC-011, TC-013, TC-019, TC-021, TC-022）。
    外部通信を行わないオフライン・モック決定論的実行により全ユニットの動作を検証する。
対応機能ID（トレーサビリティ）：
    UNIT-001, UNIT-002, UNIT-003, UNIT-004, UNIT-006, UNIT-007 (REQ-001〜REQ-007)
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

import asdoq_lint  # noqa: E402
import export_skillset  # noqa: E402


class TestAsdoqUnit001To003(unittest.TestCase):
    """UNIT-001〜UNIT-003 の単体・統合検証テストケース（TC-001〜TC-011）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dict_path = REPO_ROOT / "tools" / "asdoq_dictionary.json"
        cls.ruleset = asdoq_lint.load_dictionary(cls.dict_path)

    def test_tc001_dictionary_80_vs_79_boundary_and_canonical_names(self) -> None:
        """TC-001 (UNIT-001): 拡張辞書8カテゴリ・80件/79件境界・正準6特性名・旧表記拒否を検証する。"""
        # Arrange & Act
        summary = asdoq_lint.validate_dictionary_file(self.dict_path)

        # Assert: 80件以上、8カテゴリ網羅、正準6特性名、[ASDoQ:特性-副特性]形式
        self.assertTrue(summary["valid"])
        self.assertGreaterEqual(summary["rules_count"], 80)
        self.assertEqual(set(summary["category_counts"].keys()), {"1", "2", "3", "4", "5", "6", "7", "8"})
        self.assertEqual(summary["canonical_characteristics"]["C1_purpose"], "1. 目的適合性")
        for r in self.ruleset["active_rules"]:
            self.assertRegex(r["asdoq_label"], r"^\[ASDoQ:[^-\[\]]+-[^\[\]]+\]$")

        # RULE-811 は入力文書中の旧表記・旧タグを検出できること
        r811 = [r for r in self.ruleset["rules"] if r["id"] == "RULE-811"][0]
        self.assertIsNotNone(r811["_compiled"].search("1. \u5408\u76ee\u7684\u6027"))
        self.assertIsNotNone(r811["_compiled"].search("\u3010ASDoQ: \u7406\u89e3\u5bb9\u6613\u6027\u3011"))

        # 79件境界および旧名称混入で DictionaryValidationError が発生すること
        base_obj = json.loads(self.dict_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmpdir:
            d79 = dict(base_obj)
            d79["rules"] = base_obj["rules"][:79]
            p79 = Path(tmpdir) / "dict79.json"
            p79.write_text(json.dumps(d79, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(asdoq_lint.DictionaryValidationError):
                asdoq_lint.load_dictionary(p79)

            d_leg = json.loads(self.dict_path.read_text(encoding="utf-8"))
            d_leg["characteristics"]["C1_purpose"] = "1. \u5408\u76ee\u7684\u6027"
            p_leg = Path(tmpdir) / "dict_legacy.json"
            p_leg.write_text(json.dumps(d_leg, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(asdoq_lint.DictionaryValidationError):
                asdoq_lint.load_dictionary(p_leg)

    def test_tc002_custom_dictionary_merge_and_whitelist_masking(self) -> None:
        """TC-002 (UNIT-001): 企業カスタム辞書のNG/OK/無効化/規範ルール統合を検証する。"""
        # Arrange
        custom_obj = {
            "custom_ng_rules": [{"id": "CORP-NG-1", "ng": "ワンストップ対応", "ok": "単一窓口で処理"}],
            "custom_ok_terms": ["高速バックエンド"],
            "disabled_rule_ids": ["RULE-102"],
            "corporate_conformance_rules": [{"id": "CORP-FMT-1", "pattern": r"TODO:", "ok": "課題IDへ置換"}],
        }
        base_obj = json.loads(self.dict_path.read_text(encoding="utf-8"))

        # Act
        merged = asdoq_lint.merge_dictionaries(base_obj, custom_obj)
        doc = "# 概要\n読み手は開発者とする。目的は確認である。\n- 高速バックエンドでワンストップ対応を行う。TODO: 確認\n"
        res = asdoq_lint.analyze_document_layer0(doc, merged, profile="general")
        hit_ids = {f["rule_id"] for f in res["confirmed_findings"]}

        # Assert
        self.assertIn("CORP-NG-1", hit_ids)
        self.assertIn("CORP-FMT-1", hit_ids)
        self.assertNotIn("RULE-102", hit_ids)

    def test_tc003_dictionary_error_handling_and_cli_exit2(self) -> None:
        """TC-003 (UNIT-001): 不在辞書・JSON構文不正・必須6キー欠落で終了コード2を検証する。"""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "no_such_dict.json"
            broken_path = Path(tmpdir) / "broken.json"
            broken_path.write_text("{invalid json", encoding="utf-8")

            missing_key_dict = json.loads(self.dict_path.read_text(encoding="utf-8"))
            del missing_key_dict["rules"][0]["hint"]
            missing_key_path = Path(tmpdir) / "missing_key.json"
            missing_key_path.write_text(json.dumps(missing_key_dict, ensure_ascii=False), encoding="utf-8")

            # Act & Assert
            for p in (missing_path, broken_path, missing_key_path):
                with self.assertRaises(asdoq_lint.DictionaryValidationError):
                    asdoq_lint.load_dictionary(p)
                err_buf = io.StringIO()
                with redirect_stderr(err_buf):
                    rc = asdoq_lint.main(["--validate-dict", str(p)])
                self.assertEqual(rc, 2)

    def test_tc004_layer0_categories_crossref_and_exit_codes(self) -> None:
        """TC-004 (UNIT-002): Layer 0全8カテゴリ検査・構造クロスリファレンス4項目・テンプレートマスク・終了コードを検証する。"""
        # Arrange
        doc = (
            "# 概要\n読み手は開発者とする。目的はテストである。適用範囲は本機能とし、他機能は対象外とする（理由: 検証対象外のため）。\n\n"
            "## 非機能要求（性能・品質等）\n\n"
            "| 項目 | 期待される出力 | 期待される振る舞い |\n| :--- | :--- | :--- |\n| T1 | OK | 正常終了 |\n\n"
            "```markdown\nシステムは適切かつ高速に動作する。\n```\n\n"
            "- システムは適切に動作すると思われる。\n"
        )

        # Act
        res = asdoq_lint.analyze_document_layer0(doc, self.ruleset, profile="sw105")
        rule_ids = {f["rule_id"] for f in res["confirmed_findings"]}
        xr = res["cross_reference"]

        # Assert
        self.assertIn("RULE-101", rule_ids)
        self.assertIn("RULE-801", rule_ids)
        self.assertNotIn("RULE-102", rule_ids)
        self.assertNotIn("RULE-802", rule_ids)
        self.assertEqual(
            set(xr.keys()),
            {"purpose_scope_check", "term_cross_check", "numbers_units_table", "heading_figure_table_check"},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ng_file = Path(tmpdir) / "ng.md"
            ng_file.write_text(doc, encoding="utf-8")
            out_buf = io.StringIO()
            with redirect_stdout(out_buf):
                rc_ng = asdoq_lint.main(["--input", str(ng_file), "--profile", "sw105", "--summary"])
            self.assertEqual(rc_ng, 1)

            ok_file = Path(tmpdir) / "ok.md"
            ok_file.write_text("# 概要\n読み手は開発者とする。目的は確認である。\n本ツールは終了コード0を返す。\n", encoding="utf-8")
            out_ok = io.StringIO()
            with redirect_stdout(out_ok):
                rc_ok = asdoq_lint.main(["--input", str(ok_file), "--profile", "general", "--summary"])
            self.assertEqual(rc_ok, 0)

    def test_tc005_mermaid_10_vs_11_nodes_connection_pairs_and_captions(self) -> None:
        """TC-005 (UNIT-002): Mermaid 10/11ノード境界・[接続N]ペア検査・図表境界一致・図下表上キャプションを検証する。"""
        # Arrange
        ten_nodes = "\n".join(f"A{i} --> A{i+1}" for i in range(1, 10))
        eleven_nodes = "\n".join(f"B{i} --> B{i+1}" for i in range(1, 11))
        doc = (
            "# 概要\n読み手は設計者とする。目的は図分割検証である。適用範囲は全体とし、他は対象外とする（理由: 検証用のため）。\n"
            "表現1や代表2、設計図10%は図表参照ではないが、表1および図3を参照する。\n\n"
            "**表1：正常テーブル**\n\n| A | B |\n| :--- | :--- |\n| 1 | 2 |\n\n"
            f"```mermaid\nflowchart TD\n{ten_nodes}\nA10[\"[接続1: 出力]\"]\n```\n\n**図1：10ノード境界図**\n\n"
            "```mermaid\nflowchart TD\nC1[\"[接続1: 入力]\"] --> C2[\"[接続2: 孤立]\"]\n```\n\n**図2：接続ペア図**\n\n"
            "**図3：上配置違反11ノード図**\n"
            f"```mermaid\nflowchart TD\n{eleven_nodes}\n```\n"
        )

        # Act
        res = asdoq_lint.analyze_document_layer0(doc, self.ruleset, profile="sw205")
        hf = res["cross_reference"]["heading_figure_table_check"]
        ids = {f["rule_id"] for f in res["confirmed_findings"]}

        # Assert
        self.assertEqual(hf["missing_table_definitions"], [])
        self.assertEqual(hf["missing_figure_definitions"], [])
        self.assertEqual(len(hf["mermaid_over_10_nodes"]), 1)
        self.assertEqual(hf["mermaid_over_10_nodes"][0]["node_count"], 11)
        self.assertEqual([c["connection"] for c in hf["connection_pair_check"]["paired_connections"]], ["接続1"])
        self.assertEqual(
            [c["connection"] for c in hf["connection_pair_check"]["isolated_connection_warnings"]],
            ["接続2"],
        )
        self.assertIn("STRUCT-MERMAID-NODES", ids)
        self.assertIn("STRUCT-MERMAID-CONN", ids)
        self.assertTrue(any(v["type"] == "figure_caption_above" for v in hf["caption_position_violations"]))

    def test_tc006_slice_compression_max_items_25_26_and_latency(self) -> None:
        """TC-006 (UNIT-002): 疑義スライス50%以下圧縮・25/26件上限・推奨2〜4特性・3.0秒以内を検証する。"""
        # Arrange
        normal_lines = "\n".join(f"- 処理{i}は1秒以内で完了する明確な仕様である。" for i in range(40))
        suspect_lines = "\n".join(f"- 処理{i}は適切に動作する。" for i in range(26))
        doc = "# 概要\n読み手は開発者とする。目的は性能検証である。\n" + normal_lines + "\n" + suspect_lines

        # Act
        t0 = time.perf_counter()
        res = asdoq_lint.analyze_document_layer0(doc, self.ruleset, profile="sw105", max_items=25)
        elapsed = time.perf_counter() - t0

        # Assert
        self.assertEqual(res["omitted_counts_by_category"].get("1"), 1)
        self.assertEqual(len([f for f in res["confirmed_findings"] if f["category"] == "1"]), 25)
        self.assertLessEqual(res["compression_ratio"], 0.50)
        self.assertGreaterEqual(len(res["recommended_characteristics"]), 2)
        self.assertLessEqual(len(res["recommended_characteristics"]), 4)
        self.assertLess(elapsed, 3.0)

    def test_tc007_missing_empty_file_and_janome_stdlib_fallback(self) -> None:
        """TC-007 (UNIT-002): 不在・空ファイル終了コード2およびJanome無効時stdlibフォールバックを検証する。"""
        # Arrange & Act & Assert
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_file = Path(tmpdir) / "missing.md"
            empty_file = Path(tmpdir) / "empty.md"
            empty_file.write_text("   \n", encoding="utf-8")

            for p in (missing_file, empty_file):
                err_buf = io.StringIO()
                with redirect_stderr(err_buf):
                    rc = asdoq_lint.main(["--input", str(p)])
                self.assertEqual(rc, 2)

        with self.assertRaises(asdoq_lint.InputDocumentError):
            asdoq_lint.analyze_document_layer0("", self.ruleset)

        res = asdoq_lint.analyze_document_layer0(
            "# 概要\n読み手は設計者とする。目的は形態素解析フォールバック確認である。",
            self.ruleset,
            force_stdlib=True,
        )
        self.assertEqual(res["tokenizer_mode"], "stdlib_fallback")

    def test_tc008_decision1_mock_noul_choice_score_and_threshold_boundary(self) -> None:
        """TC-008 (UNIT-003): gemini-decision-1 モック構造化判定と閾値0.30/0.29境界を検証する。"""
        # Arrange
        slices = [
            {"slice_id": "SLICE-001", "line": 10, "section": "仕様", "text": "境界030 の曖昧候補文", "suspected_characteristic": "C4_understandability"},
            {"slice_id": "SLICE-002", "line": 11, "section": "仕様", "text": "境界029 の明確正常文", "suspected_characteristic": "C4_understandability"},
        ]
        mock_client = asdoq_lint.MockDecision1Client(fail_times=0)

        # Act
        res = asdoq_lint.evaluate_layer1_decision1(slices, decision1_mode="on", threshold=0.30, client=mock_client)

        # Assert
        self.assertEqual(res["decision1_mode"], "on (mock)")
        self.assertEqual(res["total_output_tokens"], 0)
        self.assertEqual([s["slice_id"] for s in res["retained_slices"]], ["SLICE-001"])
        self.assertEqual([s["slice_id"] for s in res["discarded_slices"]], ["SLICE-002"])
        self.assertRegex(res["retained_slices"][0]["asdoq_label"], r"^\[ASDoQ:[^-\[\]]+-[^\[\]]+\]$")

    def test_tc009_default_decision1_off_offline_fallback(self) -> None:
        """TC-009 (UNIT-003): 既定 --decision1 off 時は外部通信0回でローカルフォールバック動作する。"""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            sample = Path(tmpdir) / "doc.md"
            sample.write_text("# 概要\n読み手は開発者とする。目的は確認である。\n- 適切に処理する場合。\n", encoding="utf-8")
            out_buf = io.StringIO()

            # Act
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("HTTP must not be called in off mode")):
                with redirect_stdout(out_buf):
                    rc = asdoq_lint.main(["--input", str(sample), "--profile", "general", "--format", "json"])
            payload = json.loads(out_buf.getvalue())

        # Assert
        self.assertEqual(rc, 1)
        self.assertEqual(payload["DECISION1_MODE"], "off (local_rule_fallback)")
        self.assertEqual(payload["layer1"]["api_calls"], 0)

    def test_tc010_key_priority_1000_chunking_and_zero_question_skip(self) -> None:
        """TC-010 (UNIT-003): キー解決優先順・1,000/1,001問バッチ分割・0問スキップを検証する。"""
        # Arrange: キー優先順位
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env").write_text('GEMINI_API_KEY="env_file_secret"\n', encoding="utf-8")
            (root / ".env.local").write_text('GEMINI_API_KEY="local_file_secret"\n', encoding="utf-8")

            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
                k1, src1 = asdoq_lint.resolve_gemini_api_key(root)
                self.assertEqual((k1, src1), ("local_file_secret", "file:.env.local"))

            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "os_env_secret"}, clear=False):
                k2, src2 = asdoq_lint.resolve_gemini_api_key(root)
                self.assertEqual((k2, src2), ("os_env_secret", "env:GEMINI_API_KEY"))

        # Act & Assert: 1,000問以内(333スライス=999問)は1回、1,000問超(334スライス=1,002問)は2回分割
        c_single = asdoq_lint.MockDecision1Client(fail_times=0)
        s333 = [{"slice_id": f"S-{i}", "line": i, "section": "S", "text": "境界030"} for i in range(333)]
        res_1 = asdoq_lint.evaluate_layer1_decision1(s333, decision1_mode="on", client=c_single)
        self.assertEqual(res_1["api_calls"], 1)
        self.assertEqual(len(c_single.last_payloads[0]["questions"]), 999)

        c_multi = asdoq_lint.MockDecision1Client(fail_times=0)
        s334 = [{"slice_id": f"S-{i}", "line": i, "section": "S", "text": "境界030"} for i in range(334)]
        res_2 = asdoq_lint.evaluate_layer1_decision1(s334, decision1_mode="on", client=c_multi)
        self.assertEqual(res_2["api_calls"], 2)
        self.assertEqual(len(c_multi.last_payloads[0]["questions"]), 999)
        self.assertEqual(len(c_multi.last_payloads[1]["questions"]), 3)

        # 0問時はAPI呼び出しをスキップ
        c_skip = asdoq_lint.MockDecision1Client(fail_times=0)
        res_0 = asdoq_lint.evaluate_layer1_decision1([], decision1_mode="on", client=c_skip)
        self.assertEqual(res_0["decision1_mode"], "on_skipped (no_questions)")
        self.assertEqual(c_skip.call_count, 0)

    def test_tc011_missing_key_deprecated_flag_threshold_range_retries_and_clean_codebase(self) -> None:
        """TC-011 (UNIT-003): キー未設定・旧CLI廃止・閾値範囲外・2回リトライ・キー非露出・旧語句0件を検証する。"""
        # 1. APIキー未設定で --decision1 on かつ疑義スライスありなら終了コード2
        with tempfile.TemporaryDirectory() as tmpdir:
            doc = Path(tmpdir) / "doc.md"
            doc.write_text("# 概要\n読み手は開発者とする。目的はテストである。\n- 適切に処理する場合。\n", encoding="utf-8")
            with mock.patch.object(asdoq_lint, "resolve_gemini_api_key", return_value=(None, "unset")):
                err_buf = io.StringIO()
                with redirect_stderr(err_buf):
                    rc_nokey = asdoq_lint.main(["--input", str(doc), "--decision1", "on"])
            self.assertEqual(rc_nokey, 2)

            # キー値が設定されても --decision1 off 出力にキー生文字列は露出しない
            secret = "AIzaSyTestSecretShouldNeverLeak999"
            out_buf = io.StringIO()
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": secret}, clear=False):
                with redirect_stdout(out_buf):
                    asdoq_lint.main(["--input", str(doc), "--format", "json"])
            self.assertNotIn(secret, out_buf.getvalue())

        # 2. 旧オプション拒否（終了コード2）
        old_flag = "--" + chr(106) + chr(101) + chr(118)
        dep_err = io.StringIO()
        with redirect_stderr(dep_err):
            rc_dep = asdoq_lint.main([old_flag, "off"])
        self.assertEqual(rc_dep, 2)
        self.assertIn("--decision1", dep_err.getvalue())

        # 3. 閾値範囲外（-0.1 / 1.1）
        with self.assertRaises(ValueError):
            asdoq_lint.evaluate_layer1_decision1([], threshold=-0.1)
        with self.assertRaises(ValueError):
            asdoq_lint.evaluate_layer1_decision1([], threshold=1.1)

        # 4. 最大2回リトライ後にローカルフォールバックへ遷移
        slices = [{"slice_id": "SLICE-001", "line": 5, "section": "仕様", "text": "適切に処理する"}]
        client_ok = asdoq_lint.MockDecision1Client(fail_times=1)
        res_ok = asdoq_lint.evaluate_layer1_decision1(slices, decision1_mode="on", client=client_ok)
        self.assertEqual(res_ok["retry_count"], 1)

        client_fail = asdoq_lint.MockDecision1Client(fail_times=3)
        fb_err = io.StringIO()
        with redirect_stderr(fb_err):
            res_fb = asdoq_lint.evaluate_layer1_decision1(slices, decision1_mode="on", client=client_fail)
        self.assertEqual(res_fb["retry_count"], 2)
        self.assertEqual(res_fb["decision1_mode"], "off (local_fallback_after_error)")

        # 5. コード・辞書に旧名称/旧SDK文字列が0件
        legacy_pat = r"(?:" + chr(106) + chr(101) + chr(118) + r"|typesafe)"
        for rel in ("tools/asdoq_lint.py", "tools/asdoq_dictionary.json"):
            content = (REPO_ROOT / rel).read_text(encoding="utf-8")
            self.assertNotRegex(content.lower(), legacy_pat, f"Legacy term found in {rel}")


class TestAsdoqUnit004To007(unittest.TestCase):
    """UNIT-004〜UNIT-007 の定義ファイル・スキル配布・回帰検証テストケース（TC-013, TC-019, TC-021, TC-022）。"""

    def test_tc013_specialist_definitions_6_files_and_200_line_boundary(self) -> None:
        """TC-013 (UNIT-004): C1〜C6実在・200行以下/201行超過境界・必須6要素・旧表記と/swarm非混入を検証する。"""
        # Arrange & Act
        refs_dir = REPO_ROOT / ".agents" / "skills" / "asdoq-reviewer" / "references"
        res = asdoq_lint.validate_specialist_definitions(refs_dir, max_lines=200)

        # Assert: 実物6ファイル合格
        self.assertTrue(res["valid"], f"Specialist errors: {res['errors']}")
        self.assertEqual(len(res["files"]), 6)
        for fname, info in res["files"].items():
            self.assertLessEqual(info["line_count"], 200, fname)
            content = (refs_dir / fname).read_text(encoding="utf-8")
            self.assertNotIn("/swarm", content)
            self.assertNotIn("\u5408\u76ee\u7684\u6027", content)
            self.assertNotIn("\u3010ASDoQ:", content)

        # 201行超過や /swarm 混入時は valid=False となる境界テスト
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_refs = Path(tmpdir)
            for fname in asdoq_lint.SPECIALIST_FILES:
                text = (refs_dir / fname).read_text(encoding="utf-8")
                if fname.startswith("C1_"):
                    extra = "\n".join(f"<!-- pad {i} -->" for i in range(150))
                    text = text + "\n" + extra + "\n"
                if fname.startswith("C2_"):
                    text = text + "\n- /swarm を使ってよい。\n"
                (tmp_refs / fname).write_text(text, encoding="utf-8")
            bad_res = asdoq_lint.validate_specialist_definitions(tmp_refs, max_lines=200)
            self.assertFalse(bad_res["valid"])
            self.assertTrue(any("上限を超えています" in e for e in bad_res["errors"]))
            self.assertTrue(any("/swarm" in e for e in bad_res["errors"]))

    def test_tc019_unit006_cross_consistency_and_no_legacy_terms(self) -> None:
        """TC-019 (UNIT-006): 主要14ファイルのUNIT-006タグ、旧表記0件、agent_def_check全通過を検証する。"""
        # Arrange: 主要14ファイル（二次テンプレートにはUNIT-006を付与しないADR-002準拠も確認）
        main_14_files = (
            ".agents/AGENTS.md",
            ".agents/skills/asdoq-reviewer/SKILL.md",
            ".agents/skills/requirements-reviewer/SKILL.md",
            ".agents/skills/test-reviewer/SKILL.md",
            ".agents/skills/architecture-reviewer/SKILL.md",
            ".agents/skills/code-reviewer/SKILL.md",
            ".agents/skills/dada-process/SKILL.md",
            ".agents/skills/requirements-engineer/SKILL.md",
            ".agents/skills/test-engineer/SKILL.md",
            ".agents/skills/architect/SKILL.md",
            ".agents/skills/document-writer/SKILL.md",
            ".agents/skills/JP-Humanizer/SKILL.md",
            "docs/guidelines/asdoq_writing_rules.md",
            "docs/guidelines/asdoq_checklist.md",
            "docs/guidelines/dada_document_guidelines.md",
        )
        legacy_pat = r"(?:" + chr(106) + chr(101) + chr(118) + r"|typesafe|\u5408\u76ee\u7684\u6027|\u3010ASDoQ:|85\u4ef6)"

        # Act & Assert
        for rel in main_14_files:
            content = (REPO_ROOT / rel).read_text(encoding="utf-8")
            if rel != ".agents/skills/asdoq-reviewer/SKILL.md":
                self.assertIn("<!-- UNIT-006 / REQ-006 -->", content, f"Missing UNIT-006 tag in {rel}")
            else:
                self.assertIn("<!-- UNIT-005 / REQ-005 -->", content)
            self.assertNotRegex(content, legacy_pat, f"Legacy term found in {rel}")

        # 機械チェック (unit / skill / command) がすべて終了コード0で通ることを確認
        for mode in ("unit", "skill", "command"):
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "tools" / "agent_def_check.py"), mode],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, f"agent_def_check {mode} failed:\n{proc.stdout}\n{proc.stderr}")

    def test_tc021_export_skillset_readme_env_and_clean_terms(self) -> None:
        """TC-021 (UNIT-007): スキルセット切り出し、.env.example/.gitignore、README tips16-17、旧表記0件を検証する。"""
        import export_skillset  # type: ignore

        legacy_pat = r"(?:" + chr(106) + chr(101) + chr(118) + r"|typesafe|\u5408\u76ee\u7684\u6027|85\u4ef6|\u3010ASDoQ:)"
        # 1. リポジトリ直下ファイル群の仕様準拠と旧表記0件
        env_ex = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("GEMINI_API_KEY", env_ex)
        self.assertIn("OPENAI_API_KEY", env_ex)
        self.assertIn("ANTHROPIC_API_KEY", env_ex)
        self.assertNotRegex(env_ex, legacy_pat)

        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".env", gitignore)
        self.assertIn(".env.*", gitignore)
        self.assertIn("!.env.example", gitignore)

        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotRegex(readme, legacy_pat)
        for required_url in (
            "https://aistudio.google.com/docs/models/gemini-decision-1",
            "https://aistudio.google.com/docs/decisions-api",
            "https://antigravity.google/blog/gemini-4-hydrogen-in-google-antigravity/",
            "https://antigravity.google/blog/gemini-4-carbon-in-google-antigravity",
        ):
            self.assertIn(required_url, readme)
        self.assertIn("16. **モデルの思考レベル", readme)
        self.assertIn("17. **Antigravity `/swarm`", readme)

        # 2. asdoq-reviewer / dada-core エクスポート時の README.md と .env.example 生成検証
        with tempfile.TemporaryDirectory() as tmpdir:
            for set_name in ("asdoq-reviewer", "dada-core"):
                out_dir = Path(tmpdir) / set_name
                copied = export_skillset.export_skillset(REPO_ROOT, set_name, out_dir)
                self.assertIn("README.md", copied)
                self.assertIn(".env.example", copied)
                exp_readme = (out_dir / "README.md").read_text(encoding="utf-8")
                exp_env = (out_dir / ".env.example").read_text(encoding="utf-8")
                self.assertIn("GEMINI_API_KEY", exp_env)
                self.assertNotRegex(exp_readme, legacy_pat)
                self.assertNotRegex(exp_env, legacy_pat)
            self.assertTrue((Path(tmpdir) / "dada-core" / "tools" / "style_check.py").exists())
            self.assertTrue((Path(tmpdir) / "dada-core" / "tools" / "office_io.py").exists())

            # 3. 切り出された全4スキルセット単体で agent_def_check (skill / command) が High 0 / Mid 0 で合格することを検証
            for set_name in ("office-suite", "jp-humanizer", "asdoq-reviewer", "dada-core"):
                out_dir = Path(tmpdir) / f"check_{set_name}"
                export_skillset.export_skillset(REPO_ROOT, set_name, out_dir)
                for mode in ("skill", "command"):
                    proc_chk = subprocess.run(
                        [sys.executable, str(REPO_ROOT / "tools" / "agent_def_check.py"), mode, "--root", str(out_dir), "--summary"],
                        cwd=str(REPO_ROOT),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                    )
                    self.assertEqual(proc_chk.returncode, 0, f"{set_name} {mode} failed: {proc_chk.stdout}")
                    self.assertIn("High 0 / Mid 0", proc_chk.stdout, f"{set_name} {mode} has warnings: {proc_chk.stdout}")

    def test_tc022_export_skillset_error_exit_codes(self) -> None:
        """TC-022 (UNIT-007): 未定義スキルセット名(終了コード2)と必須ファイル欠損(終了コード1)を検証する。"""
        import export_skillset  # type: ignore

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "out_unknown"
            proc_unknown = subprocess.run(
                [sys.executable, str(REPO_ROOT / "tools" / "export_skillset.py"), "export", "--set", "unknown-set", "--out", str(out_dir)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(proc_unknown.returncode, 2)

            # 必須ファイル欠損時の FileNotFoundError と CLI終了コード1
            empty_root = Path(tmpdir) / "empty_repo"
            empty_root.mkdir()
            with self.assertRaises(FileNotFoundError):
                export_skillset.export_skillset(empty_root, "asdoq-reviewer", Path(tmpdir) / "out_fail")

            # tools/export_skillset.py のコピーを使って欠損リポジトリ時の CLI 終了コード1を検証
            tools_copy = empty_root / "tools"
            tools_copy.mkdir()
            (tools_copy / "export_skillset.py").write_text(
                (REPO_ROOT / "tools" / "export_skillset.py").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            proc_missing = subprocess.run(
                [sys.executable, str(tools_copy / "export_skillset.py"), "export", "--set", "asdoq-reviewer", "--out", str(Path(tmpdir) / "out_cli_fail")],
                cwd=str(empty_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(proc_missing.returncode, 1)


if __name__ == "__main__":
    unittest.main()
