# ライセンスおよび著作権表示 ( Attribution & License Notices )

本ディレクトリ（`.agents/skills/JP-Humanizer/`）および対応する検査ツール（`tools/style_check.py`）は、以下のオープンソースソフトウェアおよび公開知見を参考に、DADAプロセスおよびASDoQシステム開発文書品質モデル向けに独自拡張・再構築したものです。元の `yomiyasu` とは構造・ASDoQ連携・機械検証ツールの有無が異なるため、混同を防ぐ目的で名称を **`JP-Humanizer`** としています。

## 1. 原著作物（`yomiyasu`）の著作権表示とライセンス

- **プロジェクト名**: `yomiyasu` (Japanese text readability & AI-slop refinement skill)
- **リポジトリ**: https://github.com/nanaism/yomiyasu
- **解説記事**: AI-Slopな日本語を構造レベルで読みやすくするSkill『yomiyasu（よみやす）』を作りました (https://zenn.dev/algoartis/articles/0b1c731881b25c)
- **著作者**: Aiichiro Oga (`nanaism` / ALGO ARTIS Inc.)
- **ライセンス**: MIT License

```text
MIT License

Copyright (c) 2026 Aiichiro Oga (nanaism)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 2. 参考文献・定量分析の出典

- **記事名**: 生成AI以前と以後でエンジニアの文章はどう変わったのか: Qiitaの7万記事を数えてみた話
- **著者**: 逆瀬川 (@gyakuse)
- **URL**: https://nyosegawa.com/posts/qiita-writing-before-after-ai/
- **活用内容**: 生成AI普及前後のQiita約7万記事の定量比較の知見を、`JP-Humanizer` と `tools/style_check.py` に反映しています。具体的には「ダッシュ記号の約10倍急増」「太字強調の約3倍増」「全角コロン付き箇条書きの急増」「地の文の2倍長文化と読点増加」の検出・推敲基準に活用しています。

## 3. ASDoQ システム開発文書品質モデル関連文書の著作権表示とライセンス

`jp-humanizer` スキルセットに同梱される `docs/guidelines/asdoq_writing_rules.md` および `docs/guidelines/asdoq_checklist.md` は、システム開発文書品質研究会（ASDoQ）の公開著作物を元に一部改訂・翻案・再構成した派生著作物です。

- **原著作物**: 『システム開発文書品質モデル Ver. 2.0a』（本リポジトリ収録の一部改訂版: `Ver. 2.0a-3`）
- **原著作物の著作権者**: © システム開発文書品質研究会（ASDoQ：Association of System Documentation Quality）
- **ライセンス**: [ASDoQドキュメントライセンス (ADL)](https://asdoq.jp/licence/ADL-1.1.pdf)（研究会規則・著作物取扱規則: [https://asdoq.jp/rule.html](https://asdoq.jp/rule.html)）
- **利用条件**: ASDoQドキュメントライセンスの下で、著作権表示・ライセンス表示・改変履歴の明示を条件として、無償で自由な利用・複製・改変・再配布が認められています。
