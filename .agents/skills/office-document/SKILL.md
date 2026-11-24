---
name: office-document
description: Product Ownerから既存のOffice文書・PDF（.docx/.xlsx/.pptx/.pdf）の読み込み、対話しながらの直接編集・差分改訂、または完成したMarkdown成果物のOffice文書・PDFへの変換を求められた時に使用します。単体タスクとしてもDADAプロセス内でも使用できます。
---

<!-- UNIT-005 / REQ-005 -->

# Office文書・PDF 入出力スペシャリスト (Office Document Specialist)

本スキルは Word (`.docx`)・Excel (`.xlsx`)・PowerPoint (`.pptx`)・PDF (`.pdf`) の構造検査・抽出・生成・差分更新を、決定論的ツール（`tools/office_io.py`）へ委譲して実行します。

## 1. モード分岐・基本原則・思考過程（必須）
- **単体（スタンドアロン）利用時**: Office文書の検査・対話編集・変換のみの依頼では **DADAプロセス（Phase 0〜5・`SW105` 作成・`[DADA` 進行表示）を起動しない**。
- **DADAプロセス内利用時**: 通常は `docs/artifacts/` 配下の `.md` のみを作成し、明示指示時のみ `docs/artifacts/office/` へ出力する。
- **思考過程3項目**: 作業開始・完了時に **①現在地 ②判断の根拠 ③次の一手** を必ず出力する。
- **ツール委譲**: 全文をコンテキストへ読み込んで変換コードを書かず、必ず `tools/office_io.py` に `--summary` を付けて実行する。標準テンプレート（`Normal.dotm` / `Blank.potx` / `template_sheet.xlsx`）を自動適用する。

## 2. 作業手順
- **構造確認（Inspect）**:
  `python tools/office_io.py inspect --input <対象ファイルパス> --summary`
- **既存 Office / PDF の読込（Import）**:
  `python tools/office_io.py import --input <既存ファイルパス> --output <出力先.mdパス> --summary`
  （PDF のレイアウト視覚確認が必要な場合のみ `read_file` で確認する）
- **レイアウト維持の差分反映（Patch）**:
  `python tools/office_io.py patch --base <元のOfficeパス> --input <改訂後.mdパス> --output <出力先Officeパス> --summary`
- **Markdown からの新規変換（Export / Batch）**:
  `python tools/office_io.py export --input <入力.mdパス> --output <出力先Officeパス> --summary`
  一括変換時: `python tools/office_io.py batch-export --artifacts-dir docs/artifacts --out-dir docs/artifacts/office --summary`
- **単体対話編集ループ**: `import` で作業用 `.md` 化 → 議論内容を `.md` に反映（必要に応じ `JP-Humanizer` 適用）→ `patch` または `export` → `inspect --summary` で体裁確認してパスと変更サマリのみ報告する。

## 3. 失敗時の上限とエスカレーション
- ツール実行エラーやレイアウト警告の修正試行は **最大3回まで** とする。3回で解消しない場合は打ち切り、対象パスとエラー内容を報告する。

## 4. 禁止事項
- 求められていない通常の Phase 進行中に無断で Office 文書を生成すること。
- `tools/office_io.py` を使わず使い捨て変換スクリプトを書くこと、または変換目的で `.md` 全文を再読込すること。
- `docs/templates/office/` の標準テンプレートを無断改変すること、および `.md` を飛ばして直接編集すること。
- 単体依頼時に無断で DADAプロセス（`SW105` 等・`[DADA` 進行表示）を起動すること。

## 5. 完了前の自己チェック
- [ ] 思考過程3項目を出力し、単体時は DADAプロセスを起動しなかったか
- [ ] `tools/office_io.py` のコマンドと `--summary` を用いて実行し、失敗上限（3回）を守ったか
