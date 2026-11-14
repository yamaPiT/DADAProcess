#!/usr/bin/env python3
"""
ファイル名: export_skillset.py
対応ユニット: UNIT-007 (REQ-007)
責務: DADAProcessリポジトリ内の単体スキルセット（office-suite / jp-humanizer / asdoq-reviewer / dada-core）を
      外部プロジェクトへ切り出し（エクスポート）し、利用ガイド（README.md）を自動生成する。
公開インターフェース:
  - list_skillsets() -> None
  - generate_bundle_readme(set_name: str) -> str
  - export_skillset(root: Path, set_name: str, out_dir: Path) -> list[str]
  - build_parser() -> argparse.ArgumentParser
  - main() -> int
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
from pathlib import Path

# Reason: Windowsコンソール環境での文字化けを防ぐため標準出力・標準エラーをUTF-8に設定する
if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


SKILLSETS: dict[str, dict[str, object]] = {
    "office-suite": {
        "title": "Office Document Suite (Office文書・PDFの直接編集・相互変換)",
        "description": "PowerPoint / Word / Excel / PDF の読み込み・対話的な直接編集・Markdownからの生成を行う単体スキルセット（標準テンプレート同梱）",
        "paths": [
            ".agents/skills/office-document",
            "tools/office_io.py",
            "docs/templates/office",
        ],
        "pip_packages": [
            "python-docx",
            "openpyxl",
            "python-pptx",
            "pypdf",
            "pdfplumber",
            "reportlab",
            "pillow",
            "lxml",
        ],
    },
    "jp-humanizer": {
        "title": "JP-Humanizer (AI生成日本語文書の自然化・意味保持推敲)",
        "description": "AIが生成した不自然な日本語（AI-Slop）を、ID・数値・条件・否定極性を保持したまま自然な日本語へ推敲・検証する単体スキルセット（ASDoQ機械検査ツール同梱）",
        "paths": [
            ".agents/skills/JP-Humanizer",
            "tools/style_check.py",
            "tools/asdoq_lint.py",
            "tools/asdoq_dictionary.json",
            "docs/guidelines/asdoq_writing_rules.md",
            "docs/guidelines/asdoq_checklist.md",
        ],
        "pip_packages": [],
    },
    "asdoq-reviewer": {
        "title": "ASDoQ Hybrid Document Reviewer (ASDoQハイブリッド文書レビューエージェント)",
        "description": "ASDoQ文書品質モデル（6大品質特性）と拡張違反例辞書・構造クロスリファレンス解析に基づき、技術文書・論理文書・開発文書（.md / .docx / .xlsx / .pptx / .pdf）を反証駆動でレビュー・修正する単体スキルセット（既定は無料・ローカル完結。明示 `--decision1 on` 指定時は Google gemini-decision-1 連携に対応）",
        "paths": [
            ".agents/skills/asdoq-reviewer",
            ".agents/skills/JP-Humanizer",
            ".agents/skills/office-document",
            "tools/asdoq_lint.py",
            "tools/asdoq_dictionary.json",
            "tools/style_check.py",
            "tools/office_io.py",
            "docs/guidelines/asdoq_writing_rules.md",
            "docs/guidelines/asdoq_checklist.md",
            "docs/guidelines/asdoq_model_markdown.md",
            "docs/templates/office",
        ],
        "pip_packages": [],
    },
    "dada-core": {
        "title": "DADA Process Core (DADA開発プロセス本体一式)",
        "description": "要求定義(SW105)・テスト仕様(SWP6)・設計(SW205)・実装(Phase 4)のフルDADAプロセスを回すためのコアスキル・ルール・テンプレート一式",
        "paths": [
            ".agents/AGENTS.md",
            ".agents/skills/dada-process",
            ".agents/skills/context-reset",
            ".agents/skills/dada-check",
            ".agents/skills/document-writer",
            ".agents/skills/requirements-engineer",
            ".agents/skills/requirements-reviewer",
            ".agents/skills/test-engineer",
            ".agents/skills/test-reviewer",
            ".agents/skills/architect",
            ".agents/skills/architecture-reviewer",
            ".agents/skills/programmer",
            ".agents/skills/code-reviewer",
            ".agents/skills/unit-test-generator",
            ".agents/skills/asdoq-reviewer",
            ".agents/skills/JP-Humanizer",
            ".agents/skills/office-document",
            "tools/dada_check.py",
            "tools/agent_def_check.py",
            "tools/asdoq_lint.py",
            "tools/asdoq_dictionary.json",
            "tools/style_check.py",
            "tools/office_io.py",
            "tools/export_skillset.py",
            "tools/README.md",
            "docs/guidelines",
            "docs/templates",
            "docs/examples",
            "docs/process/phase5_evaluation_guide.md",
        ],
        "pip_packages": [],
    },
}


# ---------------------------------------------------------------------------
# 関数名: list_skillsets
# 対応ユニット: UNIT-007 (REQ-007)
# 責務: 切り出し可能なスキルセット一覧と同梱パスを標準出力に表示する。
# ---------------------------------------------------------------------------
def list_skillsets() -> None:
    print("# 利用可能なスキルセット一覧\n")
    for key, info in SKILLSETS.items():
        print(f"## `{key}` — {info['title']}")
        print(f"- 概要: {info['description']}")
        print("- 含まれるファイル/ディレクトリ:")
        for p in info["paths"]:  # type: ignore[union-attr]
            print(f"  - `{p}`")
        pkgs = info["pip_packages"]  # type: ignore[assignment]
        if pkgs:
            print(f"- 推奨Pythonパッケージ: `pip install {' '.join(pkgs)}`")
        print()


# ---------------------------------------------------------------------------
# 関数名: generate_bundle_readme
# 対応ユニット: UNIT-007 (REQ-007)
# 責務: 単体スキルバンドル用のREADME.md（利用手順およびライセンス表記を含む）を生成する。
# ---------------------------------------------------------------------------
def generate_bundle_readme(set_name: str) -> str:
    if set_name == "office-suite":
        return """# Office Document Suite (単体スキルバンドル)

このフォルダは、DADAProcess から切り出された **Office文書・PDF（`.docx` / `.xlsx` / `.pptx` / `.pdf`）の読み込み・直接編集・相互変換** を行う単体スキルセットです。
ソフトウェア開発プロセス（DADAプロセス Phase 0〜5）を起動せず、普段のドキュメント作成・改訂業務でそのままAIエージェント（Antigravity / Claude Code / Cursor 等）に読み込ませて使えます。

## 1. セットアップ

Python 3.8+ 環境で以下のパッケージをインストールしてください。

```bash
pip install python-docx openpyxl python-pptx pypdf pdfplumber reportlab pillow lxml
```

## 2. 含まれる構成物

- `.agents/skills/office-document/SKILL.md` : AIエージェント用スキル定義
- `tools/office_io.py` : Office文書・PDFの解析・差分編集・生成を行うCLIツール
- `docs/templates/office/` : 標準テンプレート一式（Word用 `Normal.dotm`、PowerPoint用 `Blank.potx`、Excel用 `template_sheet.xlsx`）

## 3. AIエージェントへの指示の例

- 「`spec.docx` を読み込んで、第3章の要件表に新しい行を追加して `spec_v2.docx` に保存して」
- 「`report.md` を標準テンプレートを使って Word（`.docx`）と PowerPoint（`.pptx`）に変換して」
- 「`slides.pptx` のスライド一覧を見せて。3枚目のタイトルを書き換えて」

## 4. コマンドラインでの直接実行

```bash
# 標準テンプレートの同期・確認
python tools/office_io.py init-templates

# 構造・レイアウトの確認
python tools/office_io.py inspect --input sample.pptx --summary

# Office/PDF から Markdown への抽出
python tools/office_io.py import --input sample.docx --output extracted.md --summary

# Markdown から Office/PDF への変換（標準テンプレート自動適用）
python tools/office_io.py export --input report.md --output report.docx --summary

# 既存 Office 文書の書式・レイアウト維持での差分更新
python tools/office_io.py patch --base sample.pptx --input revised.md --output sample_patched.pptx --summary
```

## 5. ライセンス・著作権表示

- 本スキルセット（`.agents/skills/office-document/`, `tools/office_io.py` 等）は **MIT License**（`Copyright (c) 2026 YAMAMOTO Masaki (yamaPiT)`、全文は同梱の `LICENSE` を参照）の下で提供されます。
- 利用者が `pip install` で導入する外部パッケージ（`python-docx`, `openpyxl`, `python-pptx`, `pypdf`, `reportlab` 等）は本バンドルには同梱されておらず、各パッケージ固有のライセンスが適用されます。
"""
    if set_name == "jp-humanizer":
        return """# JP-Humanizer (単体スキルバンドル)

このフォルダは、DADAProcess から切り出された **AI生成日本語文書の自然化・意味保持推敲（AI-Slop除去）** を行う単体スキルセットです。
他のAI（ChatGPT / Claude / Gemini 等）が出力した `.md` ファイルや技術文書の「AIっぽさ」を、**元の意味・ID・数値・条件・否定極性を1ミリも変えずに** 自然で読みやすい日本語へ推敲します。

## 1. セットアップ

Python 3.8+ の標準ライブラリのみで動作します（追加の `pip install` は不要です）。

## 2. 含まれる構成物

- `.agents/skills/JP-Humanizer/SKILL.md` : AIエージェント用スキル定義（8観点の自然化ルール）
- `.agents/skills/JP-Humanizer/LICENSE.md` : 原著作物『yomiyasu』等の著作権表示・ライセンス全文
- `tools/style_check.py` : AI-Slop検出（lint）および推敲前後の意味保持検証（snapshot / verify）を行うCLIツール
- `tools/asdoq_lint.py` / `tools/asdoq_dictionary.json` : ASDoQ拡張違反例辞書86件・形態素解析・構造クロスリファレンス抽出・図表ルール検査を行うCLIツール
- `docs/guidelines/asdoq_writing_rules.md` : ASDoQ執筆ルール12箇条
- `docs/guidelines/asdoq_checklist.md` : ASDoQ品質チェックリスト

## 3. AIエージェントへの指示の例

- 「`draft.md` を JP-Humanizer スキルを使って、意味を変えずに自然な日本語に推敲して」
- 「`article.md` に AIっぽい不自然な表現がないか `style_check.py` でチェックして直して」

## 4. 意味を壊さない3ステップ推敲コマンド

```bash
# Step 1: 推敲前の意味シグネチャ（ID・数値・単位・否定表現・見出し・表行数）を保存
python tools/style_check.py snapshot --input draft.md --summary

# Step 2: AI-Slop（不自然なAI構文・太字濫用・冗長表現等）を機械検出
python tools/style_check.py lint --input draft.md

# （AIまたは人間が draft.md を自然化推敲する）

# Step 3: 推敲後の文書が元の意味（ID・数値・否定極性）を保持しているか検証
python tools/style_check.py verify --input draft.md
```

## 5. ライセンス・著作権表示

- 本スキルセット全体は **MIT License**（`Copyright (c) 2026 YAMAMOTO Masaki (yamaPiT)`、同梱の `LICENSE` を参照）の下で提供されます。
- `.agents/skills/JP-Humanizer/` および `tools/style_check.py` は、大賀愛一郎氏（`nanaism` / ALGO ARTIS Inc.）のオープンソーススキル『`yomiyasu`』（**MIT License**, `Copyright (c) 2026 Aiichiro Oga (nanaism)`、全文は `.agents/skills/JP-Humanizer/LICENSE.md` に収録）の設計思想および逆瀬川氏（`@gyakuse`）のQiita 7万記事定量分析の知見を参考に独自再構築した派生スキルです。
- `docs/guidelines/asdoq_writing_rules.md` および `docs/guidelines/asdoq_checklist.md` は、**システム開発文書品質研究会（ASDoQ）**の『システム開発文書品質モデル Ver. 2.0a』（`© システム開発文書品質研究会（ASDoQ）`）を基にした派生著作物であり、**ASDoQドキュメントライセンス（ADL 1.1）**（https://asdoq.jp/licence/ADL-1.1.pdf）の下で提供されます。
"""
    if set_name == "asdoq-reviewer":
        return """# ASDoQ Hybrid Document Reviewer (単体スキルバンドル)

<!-- UNIT-007 / REQ-007 -->

このフォルダは、DADAProcess から切り出された **ASDoQ（システム開発文書品質研究会）のシステム開発文書品質モデル（6大品質特性）と拡張違反例辞書・構造クロスリファレンス解析に基づく反証駆動文書レビュー・修正** を行う単体スキルセットです。
DADAプロセス（Phase 0〜5）を起動せず、あらゆる技術文書・企画書・仕様書・マニュアル・論文等の品質検証と自然化推敲に単体で利用できます。

> [!IMPORTANT]
> **【重要】標準動作（既定 `--decision1 off`・ローカル完結）と、Google `gemini-decision-1` 連携の違い**
> - **標準動作（既定 `--decision1 off`・API通信なし・無料）**:
>   初期状態（`--decision1 off`）では、**Layer 0（拡張違反例辞書86件・構造クロスリファレンス抽出・Mermaid 10ノード上限／`[接続N]` 検査・図下表上キャプション検査）** と **Layer 1（ローカルルールベース選別）**、および **Layer 2（LLM自身によるASDoQ 6大品質特性別の反証駆動レビュー）** で完結します。外部API通信は一切発生しません。
> - **オプション動作（`--decision1 on`・Google Gemini Decisions API 連携）**:
>   明示的に `--decision1 on` を指定すると、Google の **`gemini-decision-1`**（`https://generativelanguage.googleapis.com/v1beta/decisions`）へ1〜1,000問単位で疑義スライスを一括送信し、出力トークン 0 で `noul` / `choice` / `score` を構造化取得して文脈上の誤検知ノイズを事前選別します（疑義スライス0件時はAPI呼び出しを自動スキップ）。APIキーは `.env.local` → `.env` → 環境変数 `GEMINI_API_KEY` から読み込みます。
>   - **トークン削減効果**: 誤検知ノイズが除外されるため、`--decision1 off` のときと比べて**メインLLM（Layer 2）のトークン使用量がさらに最大約50%減少**（全文をLLMに読ませる従来方式比で**最大約50%〜70%減少**）することが期待されます。
>   - 無料枠・有料枠の選択は Google AI Studio のプロジェクト課金設定に依存し、出力トークン 0 で低コストに動作します（レート制限・料金は公式ドキュメント参照）。

## 1. セットアップ

Python 3.8+ の標準ライブラリのみで基本動作します（追加の `pip install` は不要です。形態素解析の精度を高める場合は `pip install janome`、Word / Excel / PowerPoint / PDF も直接扱う場合は `pip install python-docx openpyxl python-pptx pypdf pdfplumber reportlab pillow lxml` を任意導入できます）。Google `gemini-decision-1` を使う場合は、`.env.example` を参考に `.env.local` または `.env`（または環境変数 `GEMINI_API_KEY`）を設定してください。

## 2. 含まれる構成物

- `.agents/skills/asdoq-reviewer/SKILL.md` : ハイブリッド・レビュースキル定義（オーケストレーター）
- `.agents/skills/asdoq-reviewer/references/C1_purpose_reviewer.md`〜`C6_conformance_reviewer.md` : ASDoQ 6大品質特性別の反証駆動レビュアー定義
- `.agents/skills/JP-Humanizer/SKILL.md`（および `LICENSE.md`）: AI生成日本語の自然化推敲スキル定義
- `.agents/skills/office-document/SKILL.md` / `tools/office_io.py` / `docs/templates/office/` : Office文書・PDF（`.docx` / `.xlsx` / `.pptx` / `.pdf`）対応ツール・標準テンプレート
- `tools/asdoq_lint.py` : Layer 0（決定論的機械検査・図表検査）＋ Layer 1（`--decision1 off` 既定／`on` 時 Google `gemini-decision-1` 連携）統合CLIツール
- `tools/asdoq_dictionary.json` : 8カテゴリ・86件の拡張違反例辞書および企業カスタム辞書領域
- `tools/style_check.py` : AI-Slop検出および修正前後の意味保持検証（snapshot / verify）CLIツール
- `docs/guidelines/asdoq_writing_rules.md` / `asdoq_checklist.md` / `asdoq_model_markdown.md` : ASDoQ文書品質ガイドライン
- `.env.example` : `GEMINI_API_KEY=""` テンプレート（実キーは `.env.local` 等へ保存しGit管理対象外とする）
- `LICENSE` : MIT License および第三者著作物（ASDoQ ADL 1.1 / `yomiyasu` MIT License）の著作権表示

## 3. 単体での文書レビュー・修正の実行方法

```bash
# 1. 拡張違反例辞書のスキーマ・正規表現検証
python tools/asdoq_lint.py --validate-dict

# 2. 対象文書の機械検査＋構造クロスリファレンス抽出（既定 --decision1 off）
python tools/asdoq_lint.py --input target_doc.md --profile general

# 3. Google gemini-decision-1 連携を有効にして検査する場合（要 GEMINI_API_KEY）
python tools/asdoq_lint.py --input target_doc.md --profile general --decision1 on

# 4. 企業カスタム辞書を追加指定して検査する場合
python tools/asdoq_lint.py --input target_doc.md --profile general --custom-dict my_custom_dict.json

# 5. 文書を修正する場合の意味保持検証（snapshot -> 修正 -> verify）
python tools/style_check.py snapshot --input target_doc.md --summary
python tools/style_check.py verify --input target_doc.md
```

## 4. 企業固有のNGワード・OK用語・規範ルールの登録方法

`tools/asdoq_dictionary.json` 末尾のカスタム領域（または `--custom-dict` で渡すJSONファイル）を編集することで、Pythonコードを書き換えずに独自の表記ルールを追加できます。

- `custom_ng_rules`: 社内禁止用語や独自違反パターンのルール配列を追加
- `custom_ok_terms`: 製品名・社内正式名称など、違反検出から除外（ホワイトリスト保護）する文字列配列を追加
- `disabled_rule_ids`: 無効化したい既定ルールID（例: `"RULE-503"`）を配列に追加
- `corporate_conformance_rules`: C6（規範適合性）として強制したい社内規定ルール配列を追加

## 5. 公式ドキュメントとライセンス表記

- Gemini Decision 1 モデル仕様: https://aistudio.google.com/docs/models/gemini-decision-1
- Gemini Decisions API ガイド: https://aistudio.google.com/docs/decisions-api
- 料金 / レート制限: https://aistudio.google.com/docs/pricing#gemini-decision / https://aistudio.google.com/docs/rate-limits#gemini-decision
- スクリプトおよびエージェント定義（`tools/asdoq_lint.py`, `tools/style_check.py`, `.agents/skills/asdoq-reviewer/` 等）は **MIT License**（`Copyright (c) 2026 YAMAMOTO Masaki (yamaPiT)`、同梱の `LICENSE` を参照）の下で提供されます。
- `tools/asdoq_dictionary.json`、`.agents/skills/asdoq-reviewer/references/C1〜C6`、および `docs/guidelines/asdoq_*.md` は、**システム開発文書品質研究会（ASDoQ）** の『システム開発文書品質モデル Ver. 2.0a』（`© システム開発文書品質研究会（ASDoQ）`）に基づき編纂された派生著作物であり、**ASDoQドキュメントライセンス（ADL 1.1）**（https://asdoq.jp/licence/ADL-1.1.pdf）の下で提供されます。また報道・技術文書・公用文の一般表記原則（NHK、共同通信社、TC協会、JTF、JIS Z 8301、文化庁「公用文作成の考え方」）を参照し、独自の検査パターンおよびBefore/After改善例として再構成しています。
- 同梱の `.agents/skills/JP-Humanizer/` および `tools/style_check.py` は、大賀愛一郎氏（`nanaism` / ALGO ARTIS Inc.）のオープンソーススキル『`yomiyasu`』（**MIT License**, `Copyright (c) 2026 Aiichiro Oga (nanaism)`、全文は `.agents/skills/JP-Humanizer/LICENSE.md` に収録）および逆瀬川氏（`@gyakuse`）のQiita定量分析の知見を参考に独自再構築した派生スキルです。
"""
    return ""


# ---------------------------------------------------------------------------
# 関数名: export_skillset
# 対応ユニット: UNIT-007 (REQ-007)
# 責務: 指定されたスキルセットのファイルをすべて検証したうえで出力先ディレクトリへコピーする。
#       必須ファイルが1件でも欠落している場合はコピーを行わず FileNotFoundError を送出する。
# ---------------------------------------------------------------------------
def export_skillset(root: Path, set_name: str, out_dir: Path) -> list[str]:
    target_sets = (
        ["office-suite", "jp-humanizer", "asdoq-reviewer", "dada-core"]
        if set_name == "all"
        else [set_name]
    )

    # Reason: 途中で欠落ファイルが見つかると不完全なバンドルが残るため、コピー前に全対象パスの存在を検証する
    for s in target_sets:
        info = SKILLSETS[s]
        for rel in info["paths"]:  # type: ignore[union-attr]
            src = root / rel
            if not src.exists():
                raise FileNotFoundError(f"必須ファイルが見つかりません: {rel} ({src})")

    copied: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    for s in target_sets:
        info = SKILLSETS[s]
        for rel in info["paths"]:  # type: ignore[union-attr]
            src = root / rel
            dst = out_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            copied.append(rel)

    if set_name in ("office-suite", "jp-humanizer", "asdoq-reviewer"):
        readme_path = out_dir / "README.md"
        if not readme_path.exists():
            readme_path.write_text(generate_bundle_readme(set_name), encoding="utf-8")
            copied.append("README.md")
    elif set_name in ("dada-core", "all"):
        src_readme = root / "README.md"
        dst_readme = out_dir / "README.md"
        if src_readme.exists() and not dst_readme.exists():
            shutil.copy2(src_readme, dst_readme)
            copied.append("README.md")

        # Reason: 新規プロジェクト向けにクリーンな初期プロセス状態ファイルと成果物ディレクトリを用意する
        proc_dir = out_dir / "docs" / "process"
        proc_dir.mkdir(parents=True, exist_ok=True)
        initial_process_files: dict[str, str] = {
            "docs/process/last_phase_summary.md": (
                "# フェーズ移行サマリー (Last Phase Summary)\n\n"
                "> 本ファイルは `context-reset` スキルにより、フェーズ移行時に自動的に上書きされます。\n"
                "> 新しいコンテキストで作業を開始するAIエージェントは、まず本ファイルを読み込んで前回の文脈を復元してください。\n\n"
                "## 完了フェーズ\n- **Phase**: —（未着手）\n- **完了日時**: —\n- **承認者**: —\n\n"
                "## 次フェーズ\n- **Phase**: —\n- **着手指示**: —\n\n"
                "## 承認済みドキュメント一覧\n"
                "| ドキュメントID | ファイルパス | 状態 |\n| :--- | :--- | :--- |\n"
                "| SW105 | `docs/artifacts/SW105_ソフトウェア要求仕様書.md` | 未作成 |\n"
                "| SWP6 | `docs/artifacts/SWP6_ソフトウェア総合テスト仕様書・報告書.md` | 未作成 |\n"
                "| SW205 | `docs/artifacts/SW205_ソフトウェアアーキテクチャ設計書.md` | 未作成 |\n"
            ),
            "docs/process/impl_progress.md": (
                "# 実装進捗台帳 (Implementation Progress)\n\n"
                "| UNIT-ID | 名称 | 実装ファイル | 実装 | テスト | 備考 |\n"
                "| :--- | :--- | :--- | :---: | :--- | :--- |\n"
            ),
            "docs/process/check_report.md": "# DADA機械チェック結果\n\n（未実行）\n",
            "docs/process/autoloop_log.md": (
                "# 自律型 工程遷移ログ (Autoloop Log)\n\n"
                "| # | 遷移 | 機械チェック | レビュー判定 | 自己校正 | 判定結果 |\n"
                "| :---: | :--- | :--- | :--- | :---: | :--- |\n"
            ),
            "docs/process/eval_report.md": (
                "# エージェント定義 評価セット実行記録 (Evaluation Report)\n\n"
                "## 集計結果\n\n"
                "| 評価ID | 対象UNIT | 試行回数 | 合格回数 | 合格率 | 閾値 | 判定 |\n"
                "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |\n"
            ),
            "docs/process/agent_def_check_report.md": "# エージェント定義 一貫性チェック結果\n\n（未実行）\n",
        }
        for rel_proc, content in initial_process_files.items():
            dst_proc = out_dir / rel_proc
            if not dst_proc.exists():
                dst_proc.write_text(content, encoding="utf-8")
                copied.append(rel_proc)

        artifacts_dir = out_dir / "docs" / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = artifacts_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")
            copied.append("docs/artifacts/.gitkeep")

    if set_name in ("asdoq-reviewer", "dada-core", "all"):
        src_env = root / ".env.example"
        dst_env = out_dir / ".env.example"
        if src_env.exists():
            shutil.copy2(src_env, dst_env)
        else:
            dst_env.write_text('GEMINI_API_KEY=""\n', encoding="utf-8")
        copied.append(".env.example")

    src_license = root / "LICENSE"
    dst_license = out_dir / "LICENSE"
    if src_license.exists():
        shutil.copy2(src_license, dst_license)
        copied.append("LICENSE")

    return copied


# ---------------------------------------------------------------------------
# 関数名: build_parser
# 対応ユニット: UNIT-007 (REQ-007)
# 責務: CLI引数パーサを構築する。
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DADAProcess から必要なスキルセットだけを別フォルダへ切り出すツール"
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_list = sub.add_parser("list", help="切り出し可能なスキルセットの一覧を表示する")
    p_list.add_argument(
        "--summary",
        action="store_true",
        help="1行サマリのみを表示する",
    )

    p_exp = sub.add_parser("export", help="指定したスキルセットを出力先フォルダへコピーする")
    p_exp.add_argument(
        "--set",
        required=True,
        choices=["office-suite", "jp-humanizer", "asdoq-reviewer", "dada-core", "all"],
        help="切り出すスキルセット名",
    )
    p_exp.add_argument(
        "--out",
        required=True,
        help="出力先ディレクトリパス",
    )
    p_exp.add_argument(
        "--summary",
        action="store_true",
        help="1行サマリのみを表示する",
    )
    return parser


# ---------------------------------------------------------------------------
# 関数名: main
# 対応ユニット: UNIT-007 (REQ-007)
# 責務: CLIエントリーポイント。正常時は0、ファイル欠落等の異常時は1を返す。
# ---------------------------------------------------------------------------
def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent

    if args.subcommand == "list":
        if getattr(args, "summary", False):
            print(f"EXPORT-SKILLSET: LIST | 利用可能: {', '.join(SKILLSETS.keys())}")
        else:
            list_skillsets()
        return 0

    if args.subcommand == "export":
        out_dir = Path(args.out).resolve()
        try:
            copied = export_skillset(root, args.set, out_dir)
        except FileNotFoundError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1
        if getattr(args, "summary", False):
            print(f"EXPORT-SKILLSET: OK | set={args.set} | items={len(copied)} | out={out_dir}")
        else:
            print(f"スキルセット '{args.set}' を {out_dir} へエクスポートしました（計 {len(copied)} 項目）:")
            for item in copied:
                print(f"  - {item}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
