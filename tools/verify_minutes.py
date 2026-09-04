#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル名：verify_minutes.py
バージョン番号：0.1
作成日：2026-09-04
プログラマ名：AI Programmer
ファイルの概要：議事録の入力パス検証、出力ファイル保存、および議事録Markdown構文検証を行うツール。
対応機能ID（トレーサビリティ）：UNIT-003, REQ-001, REQ-004, REQ-005
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# 必須見出し定義（SW105 REQ-005, SW205 3.2 UNIT-003, SWP6 4.1 TC-013/TC-014）
REQUIRED_HEADINGS: list[str] = [
    "# 会議議事録",
    "## 1. 会議概要",
    "## 2. 決定事項",
    "## 3. 討議内容",
    "## 4. TODO一覧",
    "## 5. 次回議題",
]

# 不正な日付形式パターン（YYYY/MM/DD や YYYY年MM月DD日など）
INVALID_DATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b\d{4}/\d{1,2}/\d{1,2}\b"),
    re.compile(r"\b\d{4}年\d{1,2}月\d{1,2}日\b"),
]

# 有効な日付形式パターン（YYYY-MM-DD）
VALID_DATE_PATTERN: re.Pattern[str] = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def validate_input_path(file_path: str) -> tuple[int, str]:
    """
    関数名：validate_input_path
    戻り値：tuple[int, str] - (終了コード, 出力メッセージ)
    引数：file_path (str) - 検証対象の入力ファイルパス
    関数の概要：入力パスが docs/<FileName>.txt 形式であり、ファイルが実在するか検証する。
    対応機能ID（トレーサビリティ）：UNIT-003, REQ-001
    """
    # パス文字列の正規化（バックスラッシュをスラッシュに統一）
    normalized = file_path.replace("\\", "/").strip()

    # パス形式の検証: docs/ 配下の .txt 形式であること
    parts = normalized.split("/")
    if len(parts) < 2 or parts[0] != "docs" or not normalized.endswith(".txt"):
        return 2, "入力パスは docs/<FileName>.txt 形式で指定してください"

    # ファイルの実在性確認
    p = Path(normalized)
    if not p.is_file():
        return 2, f"入力ファイルが見つかりません: {file_path}"

    return 0, f"入力検証合格: {file_path}"


def save_minutes(file_name: str, content: str, output_dir: str = "docs/artifacts") -> Path:
    """
    関数名：save_minutes
    戻り値：Path - 保存された議事録ファイルのパス
    引数：
        file_name (str) - ベースファイル名（拡張子なし、または _議事録 なし）
        content (str) - 保存する議事録のMarkdownテキスト
        output_dir (str) - 保存先ディレクトリ（既定: docs/artifacts）
    関数の概要：指定ディレクトリが存在しない場合は自動作成し、UTF-8形式で議事録ファイルを保存する。
    対応機能ID（トレーサビリティ）：UNIT-003, REQ-004
    """
    # ファイル名から不要な接尾辞を除去して正規化
    base_name = file_name
    if base_name.endswith(".txt"):
        base_name = base_name[:-4]
    if base_name.endswith("_議事録.md"):
        base_name = base_name[:-len("_議事録.md")]
    elif base_name.endswith(".md"):
        base_name = base_name[:-3]

    target_dir = Path(output_dir)
    # 保存先ディレクトリが存在しない場合は自動作成
    target_dir.mkdir(parents=True, exist_ok=True)

    target_file = target_dir / f"{base_name}_議事録.md"
    # UTF-8形式でファイル書き出し
    target_file.write_text(content, encoding="utf-8")
    return target_file


def validate_output_minutes(file_path: str) -> tuple[int, str]:
    """
    関数名：validate_output_minutes
    戻り値：tuple[int, str] - (終了コード, 出力メッセージ)
    引数：file_path (str) - 検証対象の議事録Markdownファイルパス
    関数の概要：生成された議事録ファイルの実在性、6大必須見出し、および日付書式(YYYY-MM-DD)を検証する。
    対応機能ID（トレーサビリティ）：UNIT-003, REQ-005
    """
    p = Path(file_path)
    # ファイルの実在確認
    if not p.is_file():
        return 2, f"ファイルが見つかりません: {file_path}"

    try:
        content = p.read_text(encoding="utf-8-sig")
    except Exception as exc:
        return 2, f"ファイル読み込みエラー: {exc}"

    # 必須見出しの存在確認
    lines = [ln.strip() for ln in content.splitlines()]
    for heading in REQUIRED_HEADINGS:
        # 各行に見出しが含まれているか、または行頭一致で確認
        found = any(line.startswith(heading) for line in lines)
        if not found:
            return 1, f"必須見出しが欠落しています: {heading}"

    # 不正な日付書式の検出
    for pattern in INVALID_DATE_PATTERNS:
        if pattern.search(content):
            return 1, "日付書式は YYYY-MM-DD 形式で記述してください"

    # 有効な日付書式(YYYY-MM-DD)の存在確認
    if not VALID_DATE_PATTERN.search(content):
        return 1, "日付書式は YYYY-MM-DD 形式で記述してください"

    return 0, "検証合格"


def main(argv: list[str] | None = None) -> int:
    """
    関数名：main
    戻り値：int - 終了コード（0=正常/合格, 1=不合格, 2=実行エラー/不正）
    引数：argv (list[str] | None) - コマンドライン引数
    関数の概要：CLIコマンドライン引数を解析し、サブコマンドに応じた検証を実行する。
    対応機能ID（トレーサビリティ）：UNIT-003, REQ-001, REQ-005
    """
    parser = argparse.ArgumentParser(
        description="議事録検証ツール (verify_minutes.py) - 入力パス検証および議事録構文検証"
    )
    parser.add_argument(
        "subcommand",
        choices=["check-input", "check-output"],
        help="サブコマンド: check-input（入力検証）または check-output（構文検証）"
    )
    parser.add_argument(
        "file_path",
        help="検証対象ファイルパス"
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # 引数不足や引数エラー時は終了コード2を返す
        return 2

    if args.subcommand == "check-input":
        code, msg = validate_input_path(args.file_path)
    elif args.subcommand == "check-output":
        code, msg = validate_output_minutes(args.file_path)
    else:
        code, msg = 2, f"未知のサブコマンド: {args.subcommand}"

    print(msg)
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    sys.exit(main())
