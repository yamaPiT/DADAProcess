---
name: office-document
description: Product Ownerから既存のOffice文書・PDF（.docx/.xlsx/.pptx/.pdf）の読み込み、対話しながらの直接編集・差分改訂、または完成したMarkdown成果物のOffice文書・PDFへの変換やプレゼンテーション資料（.pptx）の作成を求められた時に使用します。単体タスクとしてもDADAプロセス内でも使用できます。
---

# Office文書・PDF 入出力スペシャリスト (Office Document Specialist)

本スキルは、Word (`.docx`)・Excel (`.xlsx`)・PowerPoint (`.pptx`)・PDF (`.pdf`) の4形式をフォーマット崩れなく扱うための標準作業手順です。**LLMのトークンを消費せず決定論的ツール（`tools/office_io.py`）に委譲して**処理します。
DADAプロセスの開発工程内でのオンデマンド入出力だけでなく、**「PowerPointやWordファイルを渡して、対話しながら編集・ブラッシュアップする」といった単体（スタンドアロン）の文書作業**にもそのまま使用できます。

## 基本原則（オンデマンド・省トークン原則）

1. **2つの利用モード（DADAプロセス内 / スタンドアロン利用）**:
   - **DADAプロセス内**: 基本成果物は `docs/artifacts/` 配下の `.md` ファイルです。Product Ownerから明示的な指示がない限り、通常のPhase進行中に自動でOffice文書を生成してはなりません。
   - **スタンドアロン利用（単体でのOffice文書編集・作成）**: 「このパワポ（Word/Excel）を議論しながら編集したい」「`.md` からパワポを作って」と依頼された場合は、DADAプロセスを起動せず本スキル単体で作業します（下記「作業手順 E」参照）。
2. **LLMを介さないツールへの完全委譲（トークン節約）**:
   - Office文書の生成・変換・差分反映・構造検査を行う際、**AIが元の `.md` やXMLをコンテキストに全文読み込んで変換コードを書いてはなりません**。必ず決定論的ツール `tools/office_io.py` に `--summary` オプションを付けて実行し、1行の要約出力のみで結果を確認してください。
3. **標準テンプレートの自動適用**:
   - 新規Word文書（`.docx`）作成時は `docs/templates/office/Normal.dotm`（余白・ヘッダページ番号・自動見出し番号・MS明朝/MSゴシック）が自動適用されます。
   - 新規PowerPoint（`.pptx`）作成時は `docs/templates/office/Blank.potx`（16:9・スライドマスター罫線・メイリオ/Arial）が自動適用されます。
   - 新規Excel（`.xlsx`）作成時は `docs/templates/office/template_sheet.xlsx` が自動適用されます。
   - 別のテンプレートが指定された場合のみ `--template <パス>` で上書き指定します。

---

## 作業手順

### A. 既存のOffice文書・PDFを読み込むとき（Import / 差分開発の入口）

既存の Word仕様書、Excel管理表、PowerPoint提案書、PDF資料などをDADAプロセスの入力として読み込む場合、または一部を改訂する差分開発を行う場合は、まず `.md` に変換します。

1. **Markdownへの決定論的変換**:
   - `python tools/office_io.py import --input <既存ファイルのパス> --output <出力先.mdのパス> --summary`
   - 入力が `.pdf` で図表レイアウトの視覚確認が必要な場合のみ、Antigravityの `read_file` でPDFを確認します。
2. **DADAプロセスでの改訂**:
   - 変換された `.md` ファイル（先頭に `<!-- source_office: ... -->` が自動記録されます）をベースに、通常のDADAプロセスを `.md` 形式で進めます。

### B. 既存のOffice文書のフォーマットを崩さずに差分改訂するとき（Patch）

既存の `.docx` / `.xlsx` / `.pptx` 資産に対し、`.md` 上で行った改訂内容を元の書式・罫線・列幅・数式・スライド配置を維持したまま書き戻す場合は、`patch` サブコマンドを使用します。

1. **差分パッチの実行**:
   - `python tools/office_io.py patch --base <元のOffice文書パス> --input <改訂後の.mdパス> --output <出力先Office文書パス> --summary`
2. **構造・レイアウト検査**:
   - `python tools/office_io.py inspect --input <出力先Office文書パス> --summary`

### C. Markdown成果物をOffice文書・PDFへ新規変換するとき（Export / Batch Export）

Product Ownerから「Word（またはExcel / パワポ / PDF）に出力して」と求められた場合は、以下のコマンドを実行します（`.md` をAIが読み直す必要はありません）。

1. **単一ファイルのエクスポート**:
   - 標準テンプレート（`Normal.dotm` / `Blank.potx` / `template_sheet.xlsx`）を使用する場合:
     - `python tools/office_io.py export --input <入力.mdパス> --output <出力ファイルパス> --summary`
   - 個別テンプレートを指定する場合:
     - `python tools/office_io.py export --input <入力.mdパス> --output <出力ファイルパス> --template <テンプレートパス> --summary`
2. **全成果物の一括エクスポート**:
   - Product Ownerから「成果物一式をOffice文書に変換して」と求められた場合は、1回のコマンドで一括変換します。
     - `python tools/office_io.py batch-export --artifacts-dir docs/artifacts --out-dir docs/artifacts/office --summary`
3. **出力後の検証**:
   - `export` 実行時に自動で1行の検査サマリ（`OFFICE-INSPECT: OK | ...`）が出力されます。`WARN` が出た場合のみ `python tools/office_io.py inspect --input <出力ファイルパス>` で詳細を確認します。
   - 出力が `.pdf` の場合は、`read_file` で生成されたPDFを開き、レイアウト崩れがないか視覚確認します。

### D. 開発したプログラムのプレゼンテーション資料（`.pptx`）を作成するとき

Product Ownerから「開発したプログラムのプレゼン資料をパワポで作って」と求められた場合は、**トークン節約のため、まずツールで `SW105` / `SW205` / `SWP6` から自動抽出・生成**します。

1. **ツールによる自動抽出・PowerPoint生成（LLMトークン消費ゼロ）**:
   - 以下のコマンドで `SW105`・`SW205`・`SWP6` の要点を自動抽出し、`docs/artifacts/PRES101_開発成果プレゼンテーション.md` と `Blank.potx` 適用の `.pptx` を一括生成します。
     - `python tools/office_io.py gen-pres --summary`
2. **内容を推敲・カスタマイズする場合**:
   - 生成された `docs/artifacts/PRES101_開発成果プレゼンテーション.md`（またはひな形 `.agents/skills/office-document/references/PRES101_skeleton.md`）のみを編集します。その後、以下のコマンドで `.pptx` を再出力します（元の仕様書群を読み直す必要はありません）。
     - `python tools/office_io.py export --input docs/artifacts/PRES101_開発成果プレゼンテーション.md --output docs/artifacts/PRES101_開発成果プレゼンテーション.pptx --summary`
3. **レイアウト溢れの確認**:
   - `python tools/office_io.py inspect --input docs/artifacts/PRES101_開発成果プレゼンテーション.pptx --summary` を実行し、`warnings=0`（1スライドあたりの文字量・表行数が適正）であることを確認します。

### E. スタンドアロン利用：Office文書（パワポ・Word・Excel）を対話しながら編集するとき

DADAプロセスの開発工程ではなく、Product Ownerが既存の `.pptx` / `.docx` / `.xlsx` を渡して「ディスカッションしながらこのパワポを編集したい」と求めた場合は、以下の高速ループで対話編集を行います。

1. **初回読み込み（Markdown化）**:
   - 渡されたOffice文書を、作業用の `.md` ファイルへ変換します。
     - `python tools/office_io.py import --input <渡されたOffice文書パス> --output docs/artifacts/working_doc.md --summary`
   - 変換された `docs/artifacts/working_doc.md` を読み、スライド構成や章立てを把握してProduct Ownerとディスカッションします。
2. **対話による改訂と書き戻し（Patch または Export）**:
   - Product Ownerとの議論で決まった修正を `docs/artifacts/working_doc.md` に反映します（同環境に `JP-Humanizer` スキルがある場合は自然な日本語に整えます）。
   - 元のファイルのレイアウト・デザイン・罫線を維持して更新する場合は `patch`、新規構成として出力する場合は `export` を実行します。
     - 既存レイアウト維持: `python tools/office_io.py patch --base <元のOffice文書パス> --input docs/artifacts/working_doc.md --output <出力先Office文書パス> --summary`
     - 標準テンプレートで再生成: `python tools/office_io.py export --input docs/artifacts/working_doc.md --output <出力先Office文書パス> --summary`
3. **検査と提示**:
   - `python tools/office_io.py inspect --input <出力先Office文書パス> --summary` で文字溢れがないことを確認し、更新したファイルパスと変更点のサマリをProduct Ownerに提示します。

---

## 失敗時の上限とエスカレーション

- ツールの実行エラーやレイアウト警告の修正試行は **最大3回まで** とします。
- 3回試行しても解消しない場合は作業を打ち切り、対象ファイルパスとエラー内容をProduct Ownerへ報告して指示を仰いでください。

## 禁止事項

- **無断でのOffice変換の禁止**: Product Ownerから求められていないのに、通常のPhase進行中に自動で `.docx` / `.xlsx` / `.pptx` / `.pdf` を生成してはなりません。
- **変換目的での全文読み込み・アドホック実装の禁止**: Office変換のためにAIが `.md` 全文をコンテキストに読み込んだり、その場で使い捨てのPythonスクリプトを書いて変換してはなりません。必ず `tools/office_io.py` を使用してください。
- **標準テンプレート設定の破壊の禁止**: `Normal.dotm` や `Blank.potx` のスタイル・余白・マスター設定を無断で上書き変更してはなりません。
- **Markdown（Single Source of Truth）を飛ばした直接編集の禁止**: 内容の改訂は必ず `.md` 側で行い、`export` または `patch` でOffice文書へ反映してください。
