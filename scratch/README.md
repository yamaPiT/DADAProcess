# scratch/ — テンプレートメンテ用スクリプト

本ディレクトリは **DADAプロセスでプログラムやエージェント定義を作るときのものではありません。**
このリポジトリ（DADAProcess テンプレート）自体を改訂する開発者向けです。

実行はリポジトリのルートから行います。追加パッケージは不要です（Python 3 標準ライブラリのみ）。

```text
python scratch/linkcheck.py
python scratch/anchorcheck.py
python scratch/regress.py
python scratch/update_readme.py
```

Windows のコンソールが cp932 のときは、スクリプト側で UTF-8 出力に切り替えるか、次でもよいです。

```text
$env:PYTHONIOENCODING = "utf-8"
```

## スクリプト一覧

| ファイル | 目的 | いつ使うか |
| :--- | :--- | :--- |
| `linkcheck.py` | Markdown 内のリポジトリパス参照が実在するかを検査する | README・スキル・ガイドラインを改訂したあと |
| `anchorcheck.py` | 同一ファイル内の `[表示](#アンカー)` が、見出しスラッグまたは HTML の `<a id>` / `<a name>` に解決できるかを検査する | README の目次・章リンクを改訂したあと |
| `regress.py` | `tools/dada_check.py` の回帰テスト（合成した最小成果物で終了コードを確認） | `dada_check.py` を改訂したあと |
| `update_readme.py` | README 内の Global Rules 引用ブロック（`<RULE[user_global]>` … `</RULE[user_global]>`）を、スクリプト先頭のテンプレートで置換する | Global Rules の例文だけを一括更新したいとき |

## 注意

- **`anchorcheck.py` は HTML 明示アンカーを収集する。** README.md は日本語見出し・絵文字見出しのリンク先を安定させるため `<a id="...">` を置いている。見出しテキストから GitHub 方式で作ったスラッグだけを正とすると、目次が誤ってリンク切れになる。HTML id を廃止してスラッグに統一しないこと。
- **`update_readme.py` は README.md を上書きする。** 実行前に diff を確認すること。カレントディレクトリはリポジトリルートであること。
- 検査対象ファイルの一覧は、各スクリプト先頭の `TARGETS`（`regress.py` は対象外）が正である。新しいガイド文書を足したら `linkcheck.py` / `anchorcheck.py` の対象も更新する。
