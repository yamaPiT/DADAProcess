# docs/templates/office/（Office文書テンプレート格納ディレクトリ）

本ディレクトリには、Markdown成果物（`.md`）を **Word (`.docx`)・Excel (`.xlsx`)・PowerPoint (`.pptx`)** へ変換する際の標準テンプレートを格納します。

## 標準テンプレート一覧（優先使用）

| ファイル | 対象形式 | 主な設定・特徴 |
| :--- | :--- | :--- |
| `Normal.dotm` | Word (`.docx`) **【既定】** | 余白（上28.6mm・下左右30mm）、右寄せページ番号ヘッダ、見出し1〜5（MSゴシック/Arial＋自動階層採番 `1.` / `1.1` / `1.1.1` / `(1)`）、本文（MS明朝/Century 10.5pt・`Normal Indent`）、箇条書き階層 |
| `Blank.potx` | PowerPoint (`.pptx`) **【既定】** | 16:9ワイド画面、スライドマスター上下区切り線、フォントスキーム（メイリオ/Arial）、タイトルスライド・タイトルとコンテンツ・スライド番号プレースホルダ |
| `template_sheet.xlsx` | Excel (`.xlsx`) **【既定】** | 濃紺ヘッダ行、グリッド細線、先頭行固定（Freeze Panes）、テキスト折り返し |
| `template_document.docx` | Word (`.docx`) | `Normal.dotm` から正規化した `.docx` 形式の同期バックアップ |
| `template_slide.pptx` | PowerPoint (`.pptx`) | `Blank.potx` から正規化した `.pptx` 形式の同期バックアップ |

## 運用ルール

1. **自動適用**:
   `python tools/office_io.py export` や `gen-pres`、`batch-export` を実行する際、`--template` を省略すると本ディレクトリの **`Normal.dotm`（Word用）**、**`Blank.potx`（PowerPoint用）**、**`template_sheet.xlsx`（Excel用）** が自動適用されます。
2. **個別テンプレートの指定**:
   別の企業テンプレートを一時的に適用したい場合は `--template <パス>` で指定します（`.dotm` / `.dotx` / `.docx` / `.potx` / `.potm` / `.pptx` / `.xlsx` に対応）。
3. **同期の更新**:
   `Normal.dotm` または `Blank.potx` を差し替えた後に `python tools/office_io.py init-templates` を実行すると、`template_document.docx` と `template_slide.pptx` も同期されます。
