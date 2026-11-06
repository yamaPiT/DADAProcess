#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DADA Process スキルセット切り出し（バンドルエクスポート）ツール (export_skillset.py)

目的:
    DADAプロセスのリポジトリに含まれる3種類のスキルセット
      1. dada-core    : DADAプロセス本体（開発プロセス一式）
      2. office-suite : Office文書・PDFを扱うスキルセット（単体リポジトリ化可能）
      3. jp-humanizer : 人間らしい自然な日本語に変換するスキルセット（単体リポジトリ化可能）
    について、依存するスキル（`.agents/skills/`）、決定論的ツール（`tools/`）、
    知識・テンプレート（`docs/guidelines/`, `docs/templates/`）を漏れなく抽出し、
    独立した別リポジトリ・別プロジェクトへそのままコピーできるディレクトリを生成する。

前提:
    Python 3.8 以降の標準ライブラリのみ。外部依存なし。

使い方:
    python tools/export_skillset.py list
    python tools/export_skillset.py export --set <office-suite|jp-humanizer|dada-core|all> --out <出力先ディレクトリ> [--summary]

終了コード:
    0 = 成功 / 1 = 検証警告あり / 2 = 引数・実行エラー
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional


SKILLSETS: Dict[str, Dict[str, object]] = {
    "office-suite": {
        "title": "Office Document Suite（Word / Excel / PowerPoint / PDF 入出力スキルセット）",
        "description": (
            "既存のOffice文書・PDFの読み込み、対話しながらの差分編集、テンプレート（Normal.dotm / Blank.potx）を"
            "用いた新規文書変換を、LLMトークンを節約して行う独立スキルセット。"
        ),
        "paths": [
            ".agents/skills/office-document",
            "tools/office_io.py",
            "docs/templates/office",
        ],
        "requirements": "pip install python-docx openpyxl python-pptx pypdf pdfplumber reportlab pillow lxml",
        "standalone_usage": [
            "「このパワポ（Word/Excel）を読み込んで、ディスカッションしながら一緒に編集して」",
            "「この .md ファイルを標準テンプレートで Word（.docx）とパワポ（.pptx）に変換して」",
        ],
    },
    "jp-humanizer": {
        "title": "JP-Humanizer（AIっぽい日本語を自然な人間らしい日本語に直すスキルセット）",
        "description": (
            "他のAIが書いた .md ファイルや技術文書・仕様書の「AIっぽい不自然な書きぶり（AI-Slop）」を、"
            "元の意味・数値・ID・条件を100%保持したまま人間らしい自然な日本語へ構造推敲・検査する独立スキルセット。"
        ),
        "paths": [
            ".agents/skills/JP-Humanizer",
            "tools/style_check.py",
            "docs/guidelines/asdoq_writing_rules.md",
            "docs/guidelines/asdoq_checklist.md",
        ],
        "requirements": "追加パッケージ不要（Python 3.8以降の標準ライブラリのみで動作）",
        "standalone_usage": [
            "「他のAIが作ったこの .md ファイルを、JP-Humanizer スキルで人間っぽく自然な日本語に書き直して」",
            "「この文書のAIっぽい表現や読みにくい箇所を style_check.py と JP-Humanizer で厳しくチェックして」",
        ],
    },
    "dada-core": {
        "title": "DADA Process Core（人間×AI 協同アジャイル開発プロセス本体）",
        "description": (
            "要求定義（Phase 1）→ 総合テスト仕様（Phase 2）→ アーキテクチャ設計（Phase 3）→ "
            "実装・総合テスト報告（Phase 4）→ 人間評価（Phase 5）を回すDADAプロセス本体。"
        ),
        "paths": [
            ".agents/AGENTS.md",
            ".agents/skills/dada-process",
            ".agents/skills/requirements-engineer",
            ".agents/skills/requirements-reviewer",
            ".agents/skills/test-engineer",
            ".agents/skills/test-reviewer",
            ".agents/skills/architect",
            ".agents/skills/architecture-reviewer",
            ".agents/skills/programmer",
            ".agents/skills/code-reviewer",
            ".agents/skills/context-reset",
            ".agents/skills/dada-check",
            ".agents/skills/unit-test-generator",
            ".agents/skills/document-writer",
            ".agents/skills/context7-mcp",
            "tools/dada_check.py",
            "tools/agent_def_check.py",
            "docs/guidelines",
            "docs/templates/IEEE29148_2018_SRS.md",
            "docs/templates/agent",
            "docs/process",
            "docs/artifacts",
        ],
        "requirements": "追加パッケージ不要（Python 3.8以降の標準ライブラリのみで動作）",
        "standalone_usage": [
            "「DADAプロセスで開発を開始してください。[作りたいシステムの概要]」",
        ],
    },
}


def generate_bundle_readme(set_name: str, info: Dict[str, object]) -> str:
    title = str(info["title"])
    desc = str(info["description"])
    paths = list(info["paths"])  # type: ignore[arg-type]
    reqs = str(info["requirements"])
    usages = list(info["standalone_usage"])  # type: ignore[arg-type]

    lines = [
        f"# {title}",
        "",
        f"> 本ディレクトリは、DADA Process リポジトリから `python tools/export_skillset.py export --set {set_name}` によって切り出された独立スキルセットです。",
        "",
        "## 1. 概要",
        desc,
        "",
        "## 2. 同梱されているファイル・ディレクトリ",
    ]
    for p in paths:
        lines.append(f"- `{p}`")
    lines.extend([
        "",
        "## 3. 動作環境・事前準備",
        f"- Python 3.8 以降",
        f"- 依存パッケージ: `{reqs}`",
        "",
        "## 4. 使い方（チャットでの指示例）",
        "このフォルダを Antigravity 2.0（または Claude Code / Cursor / GitHub Copilot / Codex）で開き、チャットで以下のように指示してください。",
        "",
    ])
    for u in usages:
        lines.append(f"- {u}")
    lines.extend([
        "",
        "## 5. ライセンス・著作権表示",
        "- スキル・スクリプト本体: **MIT License** (`Copyright (c) 2026 YAMAMOTO Masaki (yamaPiT)`)",
    ])
    if set_name in ("jp-humanizer", "dada-core", "all"):
        lines.extend([
            "- `docs/guidelines/asdoq_*.md`: 公開されている原著作物『システム開発文書品質モデル Ver. 2.0a』（© システム開発文書品質研究会（ASDoQ））を元に一部改訂・翻案した派生著作物（Ver. 2.0a-3 ほか）であり、**ASDoQドキュメントライセンス (ADL)**（https://asdoq.jp/rule.html / https://asdoq.jp/licence/ADL-1.1.pdf）の下で無償かつ自由に利用・複製・改変・再配布できます。",
        ])
    if set_name in ("jp-humanizer", "all"):
        lines.extend([
            "- `.agents/skills/JP-Humanizer/`: 原著作物 `yomiyasu`（`Copyright (c) 2026 Aiichiro Oga (nanaism)`, **MIT License**, https://github.com/nanaism/yomiyasu）の設計思想を参考に独自拡張した派生スキルです（詳細は `.agents/skills/JP-Humanizer/LICENSE.md`）。",
        ])
    lines.append("")
    return "\n".join(lines)


def export_skillset(root: Path, set_name: str, out_dir: Path) -> List[str]:
    if set_name == "all":
        target_sets = ["dada-core", "office-suite", "jp-humanizer"]
    else:
        target_sets = [set_name]

    copied: List[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    for sname in target_sets:
        info = SKILLSETS[sname]
        for rel_p in info["paths"]:  # type: ignore[union-attr]
            src = root / str(rel_p)
            dst = out_dir / str(rel_p)
            if not src.exists():
                continue
            if src.is_dir():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            copied.append(str(rel_p))

    # LICENSEファイルを常に出力先ルートへ同梱する
    lic_src = root / "LICENSE"
    if lic_src.exists():
        shutil.copy2(lic_src, out_dir / "LICENSE")
        copied.append("LICENSE")

    # 単体切り出し時は専用READMEを生成する
    if set_name in ("office-suite", "jp-humanizer"):
        info = SKILLSETS[set_name]
        readme_path = out_dir / "README.md"
        readme_path.write_text(generate_bundle_readme(set_name, info), encoding="utf-8")
        copied.append("README.md")

    return copied


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DADA Process スキルセット切り出し（バンドルエクスポート）ツール (export_skillset.py)"
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("list", help="切り出し可能な3種類のスキルセットと構成ファイル一覧を表示する")

    p_exp = sub.add_parser("export", help="指定したスキルセットを別ディレクトリへ切り出す")
    p_exp.add_argument(
        "--set",
        dest="skillset",
        required=True,
        choices=["office-suite", "jp-humanizer", "dada-core", "all"],
        help="切り出すスキルセット名",
    )
    p_exp.add_argument("--out", required=True, help="出力先ディレクトリパス")
    p_exp.add_argument("--summary", action="store_true", help="1行サマリのみ出力する")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    root = Path(__file__).resolve().parents[1]

    if args.subcommand == "list":
        print("# DADA Process スキルセット一覧（3つの独立モジュール）\n")
        for key, info in SKILLSETS.items():
            print(f"## `{key}` — {info['title']}")
            print(f"- 説明: {info['description']}")
            print(f"- 構成パス: {', '.join(f'`{p}`' for p in info['paths'])}")  # type: ignore[union-attr]
            print(f"- 必要環境: {info['requirements']}\n")
        return 0

    if args.subcommand == "export":
        out_dir = Path(args.out)
        copied = export_skillset(root, args.skillset, out_dir)
        summary = f"SKILLSET-EXPORT: OK | set={args.skillset} | out={out_dir.as_posix()} | copied={len(copied)}"
        if args.summary:
            print(summary)
        else:
            print(f"# スキルセット切り出し完了: `{args.skillset}`\n")
            print(f"- サマリ: `{summary}`")
            print(f"- 出力先: `{out_dir.as_posix()}`")
            for c in copied:
                print(f"  - `{c}`")
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    sys.exit(main())
