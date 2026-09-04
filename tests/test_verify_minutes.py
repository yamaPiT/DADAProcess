#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル名：test_verify_minutes.py
バージョン番号：0.1
作成日：2026-09-04
プログラマ名：AI Programmer
ファイルの概要：議事録検証ツール（verify_minutes.py）の単体テストコード。
対応機能ID（トレーサビリティ）：UNIT-004, REQ-001, REQ-004, REQ-005
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# tools ディレクトリを sys.path に追加してインポート可能にする
TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import verify_minutes


class TestVerifyMinutes(unittest.TestCase):
    """
    verify_minutes.py の単体テストクラス。
    対応機能ID: UNIT-004
    """

    def setUp(self) -> None:
        """テスト前処理：一時ディレクトリを作成して作業環境を構築する。"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

        # docs および docs/artifacts ディレクトリを準備
        os.makedirs("docs", exist_ok=True)
        os.makedirs("docs/artifacts", exist_ok=True)

    def tearDown(self) -> None:
        """テスト後処理：作業環境を元に戻し一時ディレクトリを削除する。"""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -----------------------------------------------------------------------
    # 入力パス検証テスト（REQ-001 / TC-001 〜 TC-004）
    # -----------------------------------------------------------------------

    def test_tc001_check_input_valid_file(self) -> None:
        """
        対応テストID: TC-001
        対象要件: REQ-001
        シナリオ: 実在する会議メモパスを指定して入力検証スクリプトを実行する
        """
        # Arrange (準備): docs/sample.txt を作成する
        sample_path = Path("docs/sample.txt")
        sample_path.write_text("日時: 2026-09-04\n会議メモ本文", encoding="utf-8")

        # Act (実行): validate_input_path を実行する
        code, msg = verify_minutes.validate_input_path("docs/sample.txt")

        # Assert (検証): 終了コード0であり、エラーメッセージが出力されないこと
        self.assertEqual(code, 0)
        self.assertIn("入力検証合格", msg)

    def test_tc002_check_input_not_found(self) -> None:
        """
        対応テストID: TC-002
        対象要件: REQ-001
        シナリオ: 存在しない会議メモパスを指定して入力検証スクリプトを実行する
        """
        # Arrange (準備): docs/not_found.txt が存在しないことを確認する
        non_existent_path = "docs/not_found.txt"
        self.assertFalse(Path(non_existent_path).exists())

        # Act (実行): validate_input_path を実行する
        code, msg = verify_minutes.validate_input_path(non_existent_path)

        # Assert (検証): 終了コード2を出力し、所定のエラーメッセージが出力されること
        self.assertEqual(code, 2)
        self.assertEqual(msg, f"入力ファイルが見つかりません: {non_existent_path}")

    def test_tc003_check_input_invalid_extension(self) -> None:
        """
        対応テストID: TC-003
        対象要件: REQ-001
        シナリオ: 不正な拡張子のファイルを指定して入力検証スクリプトを実行する
        """
        # Arrange (準備): docs/sample.docx を作成する
        docx_path = Path("docs/sample.docx")
        docx_path.write_text("Dummy binary content", encoding="utf-8")

        # Act (実行): validate_input_path を実行する
        code, msg = verify_minutes.validate_input_path("docs/sample.docx")

        # Assert (検証): 終了コード2を出力し、形式不正エラーメッセージが出力されること
        self.assertEqual(code, 2)
        self.assertEqual(msg, "入力パスは docs/<FileName>.txt 形式で指定してください")

    def test_tc004_check_input_invalid_directory(self) -> None:
        """
        対応テストID: TC-004
        対象要件: REQ-001
        シナリオ: 不正なディレクトリパスを指定して入力検証スクリプトを実行する
        """
        # Arrange (準備): other/sample.txt を作成する
        os.makedirs("other", exist_ok=True)
        other_path = Path("other/sample.txt")
        other_path.write_text("Other dir note", encoding="utf-8")

        # Act (実行): validate_input_path を実行する
        code, msg = verify_minutes.validate_input_path("other/sample.txt")

        # Assert (検証): 終了コード2を出力し、形式不正エラーメッセージが出力されること
        self.assertEqual(code, 2)
        self.assertEqual(msg, "入力パスは docs/<FileName>.txt 形式で指定してください")

    # -----------------------------------------------------------------------
    # 議事録保存機能テスト（REQ-004 / TC-011 〜 TC-012）
    # -----------------------------------------------------------------------

    def test_tc011_save_minutes_utf8(self) -> None:
        """
        対応テストID: TC-011
        対象要件: REQ-004
        シナリオ: 議事録テキストを所定パスにUTF-8文字コードで保存する
        """
        # Arrange (準備): 保存先ディレクトリが存在する状態でコンテンツを準備
        content = "# 会議議事録\n## 1. 会議概要\n日時: 2026-09-04\n日本語テスト文字"

        # Act (実行): save_minutes を呼び出してファイルを保存
        saved_file = verify_minutes.save_minutes("sample_01", content, output_dir="docs/artifacts")

        # Assert (検証): docs/artifacts/sample_01_議事録.md が実在し、UTF-8で正しく読み出せること
        expected_path = Path("docs/artifacts/sample_01_議事録.md")
        self.assertTrue(expected_path.is_file())
        self.assertEqual(saved_file, expected_path)
        read_content = expected_path.read_text(encoding="utf-8")
        self.assertEqual(read_content, content)

    def test_tc012_save_minutes_auto_create_dir(self) -> None:
        """
        対応テストID: TC-012
        対象要件: REQ-004
        シナリオ: 保存先ディレクトリが存在しない状態で自動作成して保存する
        """
        # Arrange (準備): 保存先ディレクトリ docs/new_artifacts を削除して未存在にする
        custom_dir = "docs/new_artifacts"
        if os.path.exists(custom_dir):
            shutil.rmtree(custom_dir)
        self.assertFalse(os.path.exists(custom_dir))
        content = "# 会議議事録\n## 1. 会議概要\n日時: 2026-09-04"

        # Act (実行): ディレクトリが存在しない状態で save_minutes を実行
        saved_file = verify_minutes.save_minutes("sample_02", content, output_dir=custom_dir)

        # Assert (検証): ディレクトリが自動作成され、ファイルが生成されていること
        expected_path = Path(custom_dir) / "sample_02_議事録.md"
        self.assertTrue(os.path.isdir(custom_dir))
        self.assertTrue(expected_path.is_file())
        self.assertEqual(saved_file, expected_path)

    # -----------------------------------------------------------------------
    # 議事録構文検証テスト（REQ-005 / TC-013 〜 TC-016）
    # -----------------------------------------------------------------------

    def test_tc013_check_output_valid_minutes(self) -> None:
        """
        対応テストID: TC-013
        対象要件: REQ-005
        シナリオ: 全必須見出しおよび有効な日付書式を含む議事録ファイルを検証する
        """
        # Arrange (準備): 全必須見出しと YYYY-MM-DD を含む有効な議事録を作成
        valid_content = (
            "# 会議議事録\n\n"
            "## 1. 会議概要\n"
            "- 日時: 2026-09-04 10:00-11:00\n"
            "- 場所: 第1会議室\n\n"
            "## 2. 決定事項\n"
            "- リリース日は2026-11-30とする。\n\n"
            "## 3. 討議内容\n"
            "- スケジュールについて議論した。\n\n"
            "## 4. TODO一覧\n"
            "| タスク内容 | 担当者 | 期限 |\n"
            "| :--- | :--- | :--- |\n"
            "| 設計作成 | 佐藤 | 2026-09-15 |\n\n"
            "## 5. 次回議題\n"
            "- 進捗確認\n"
        )
        file_path = Path("docs/artifacts/valid_議事録.md")
        file_path.write_text(valid_content, encoding="utf-8")

        # Act (実行): validate_output_minutes を実行する
        code, msg = verify_minutes.validate_output_minutes(str(file_path))

        # Assert (検証): 終了コード0を出力し「検証合格」を出力すること
        self.assertEqual(code, 0)
        self.assertEqual(msg, "検証合格")

    def test_tc014_check_output_missing_heading(self) -> None:
        """
        対応テストID: TC-014
        対象要件: REQ-005
        シナリオ: 必須見出し「## 2. 決定事項」が欠落した議事録ファイルを検証する
        """
        # Arrange (準備): 「## 2. 決定事項」を含まない議事録を作成
        missing_content = (
            "# 会議議事録\n\n"
            "## 1. 会議概要\n"
            "- 日時: 2026-09-04\n\n"
            "## 3. 討議内容\n"
            "- 議論内容\n\n"
            "## 4. TODO一覧\n"
            "| タスク内容 | 担当者 | 期限 |\n"
            "| :--- | :--- | :--- |\n"
            "| タスク | 担当 | 2026-09-15 |\n\n"
            "## 5. 次回議題\n"
            "- 次回議題\n"
        )
        file_path = Path("docs/artifacts/missing_decision_議事録.md")
        file_path.write_text(missing_content, encoding="utf-8")

        # Act (実行): validate_output_minutes を実行する
        code, msg = verify_minutes.validate_output_minutes(str(file_path))

        # Assert (検証): 終了コード1を出力し欠落見出し名を出力すること
        self.assertEqual(code, 1)
        self.assertEqual(msg, "必須見出しが欠落しています: ## 2. 決定事項")

    def test_tc015_check_output_file_not_found(self) -> None:
        """
        対応テストID: TC-015
        対象要件: REQ-005
        シナリオ: 存在しない議事録ファイルパスを指定して構文検証スクリプトを実行する
        """
        # Arrange (準備): 存在しないパスを指定
        non_existent_file = "docs/artifacts/non_existent_議事録.md"
        self.assertFalse(Path(non_existent_file).exists())

        # Act (実行): validate_output_minutes を実行する
        code, msg = verify_minutes.validate_output_minutes(non_existent_file)

        # Assert (検証): 終了コード2を出力しファイル非存在エラーを出力すること
        self.assertEqual(code, 2)
        self.assertEqual(msg, f"ファイルが見つかりません: {non_existent_file}")

    def test_tc016_check_output_invalid_date_format(self) -> None:
        """
        対応テストID: TC-016
        対象要件: REQ-005
        シナリオ: 日付書式がYYYY-MM-DDではない議事録ファイルを検証する
        """
        # Arrange (準備): 日付が 2026/09/04 とスラッシュ表記された議事録を作成
        bad_date_content = (
            "# 会議議事録\n\n"
            "## 1. 会議概要\n"
            "- 日時: 2026/09/04\n\n"
            "## 2. 決定事項\n"
            "- 決定事項あり\n\n"
            "## 3. 討議内容\n"
            "- 討議内容\n\n"
            "## 4. TODO一覧\n"
            "| タスク内容 | 担当者 | 期限 |\n"
            "| :--- | :--- | :--- |\n"
            "| タスク | 担当 | 2026/09/15 |\n\n"
            "## 5. 次回議題\n"
            "- 次回議題\n"
        )
        file_path = Path("docs/artifacts/bad_date_議事録.md")
        file_path.write_text(bad_date_content, encoding="utf-8")

        # Act (実行): validate_output_minutes を実行する
        code, msg = verify_minutes.validate_output_minutes(str(file_path))

        # Assert (検証): 終了コード1を出力し、日付書式エラーメッセージを出力すること
        self.assertEqual(code, 1)
        self.assertEqual(msg, "日付書式は YYYY-MM-DD 形式で記述してください")

    # -----------------------------------------------------------------------
    # CLIエントリーポイント (main) テスト
    # -----------------------------------------------------------------------

    def test_cli_main_check_input_and_output(self) -> None:
        """
        CLI エントリーポイント main() の動作検証。
        """
        # check-input 正常系
        sample_path = Path("docs/sample.txt")
        sample_path.write_text("2026-09-04", encoding="utf-8")
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            code = verify_minutes.main(["check-input", "docs/sample.txt"])
            self.assertEqual(code, 0)
            self.assertIn("入力検証合格", fake_out.getvalue())

        # check-output 正常系
        valid_content = (
            "# 会議議事録\n## 1. 会議概要\n2026-09-04\n"
            "## 2. 決定事項\n## 3. 討議内容\n## 4. TODO一覧\n## 5. 次回議題\n"
        )
        out_path = Path("docs/artifacts/cli_valid_議事録.md")
        out_path.write_text(valid_content, encoding="utf-8")
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            code = verify_minutes.main(["check-output", str(out_path)])
            self.assertEqual(code, 0)
            self.assertIn("検証合格", fake_out.getvalue())


if __name__ == "__main__":
    unittest.main()
