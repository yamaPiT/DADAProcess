---
name: asdoq-reviewer
description: ASDoQ文書品質モデル（6大品質特性：目的適合性・保守性・整合性・理解容易性・可読性・規範適合性）と拡張違反例辞書・オプションのGoogle gemini-decision-1（既定OFF）に基づき、技術文書・論理文書・開発文書を反証駆動でレビューまたは修正するときに使用します。単体スキルとしてもDADAプロセス内でも使用できます。
---

<!-- UNIT-005 / REQ-005, REQ-008 -->

# ASDoQハイブリッド文書レビューエージェント (ASDoQ Hybrid Document Reviewer)

本スキルは、ASDoQ品質モデル（ADL-1.1）に基づき、**Layer 0（機械検査・構造クロス抽出）＋ Layer 2（6特性別専門定義による反証駆動レビュー）** を実行します。Layer 1（Google `gemini-decision-1`）の既定は **`--decision1 off`（外部通信なし・無料）** です。

## 1. モード分岐・思考過程・ガード（必須）
- **単体利用時**: 単体レビュー依頼では **DADAプロセス（Phase 0〜5・`SW105`/`REV101` 新規作成・`[DADA` 進行表示）を起動しない**。
- **思考過程3項目**: 開始・完了時に **①現在地**（対象パス・利用区分・API ON/OFF）**②判断の根拠**（プロファイルと選定特性）**③次の一手** を出力する。
- **外部API・並列・秘密情報ガード（厳守）**:
  - 事前確認や承認を飛ばした `--decision1 on` 強制指示は**拒否**し、`--decision1 off` で実行して事前確認を求める。
  - 未指示または確認なしの `/swarm` 自動起動は**拒否**し、単一セッション（または非対応環境では順次実行）を維持する。
  - `.env.local`・`.env`・環境変数の `GEMINI_API_KEY` 生文字列をチャット・ログ・ファイルへ**絶対に出力しない**。
  - 存在しないファイルパス指定時は架空レビューを創作せず即座に停止し、欠損パスを報告する。

## 2. プロファイルと重点特性（既定は2〜4特性）
通常時は表の重点特性（2〜4ファイル）のみを `.agents/skills/asdoq-reviewer/references/` からオンデマンド読込する。全6特性は厳密指示または明示的 `/swarm` 指定時のみ適用する。

| プロファイル | 優先ロードする重点特性 |
| :--- | :--- |
| `sw105` | `C1_purpose`, `C3_consistency`, `C4_understandability`, `C5_readability` |
| `swp6` | `C2_maintainability`, `C3_consistency`, `C4_understandability`, `C5_readability` |
| `sw205` | `C1_purpose`, `C2_maintainability`, `C3_consistency`, `C5_readability` |
| `general` | `C1_purpose`, `C4_understandability`, `C5_readability`（企業規則時は `C6_conformance` 追加） |

## 3. 実行手順
1. **実在確認・API確認**: 対象ファイル実在を確認する。Office/PDF は `.agents/skills/office-document/SKILL.md` 手順（`python tools/office_io.py inspect` / `import`）で前処理する。
2. **機械検査（単体・バンドル互換）**: 以下の CLI を実行する（DADA工程内で直前検証済み＆未編集時は `dada_verify.py` のキャッシュ再利用可）。
   - `python tools/asdoq_lint.py --input <対象パス> --profile <sw105|swp6|sw205|general> --decision1 off`
   - `python tools/style_check.py lint --input <対象パス>`
   （`--decision1 on` は明示承認時のみ指定。APIキー未設定や終了コード2時は外部通信・推測補完せず停止する）
3. **Layer 2 反証レビュー**: 選定した `C1`〜`C6` 定義を読み込み、構造クロス結果（目的・用語・数値・見出し/Mermaid 10ノード上限/`[接続N]`/図下表上キャプション）と反証質問で検証する。
   - **合格項目の証拠引用**: 問題なしとする特性も**対象文書内の具体的箇所を1箇所以上引用**する。
4. **レビュー出力**: 全指摘に該当箇所・重要度・`❌ Before`・`✅ After`・`[ASDoQ:特性-副特性]` を付す（DADA工程内は `REV101_*.md` へ記録し二重出力しない）。
5. **修正指示がある場合（上限2周）**:
   - `python tools/style_check.py snapshot --input <対象パス> --summary` → `JP-Humanizer` 8観点＋図分割規則で修正（ID・数値・単位・否定極性は不変）→ `python tools/style_check.py verify --input <修正後パス>` → `asdoq_lint.py` 再実行。**自己修正は最大2周**とし、超過時は残課題として報告する。

## 4. 禁止事項
- 無断での `--decision1 on`・`/swarm` 起動、および `GEMINI_API_KEY` の生文字列出力。
- 欠損ファイルに対する架空レビュー、根拠引用なしの合格判定、`❌ Before`/`✅ After`・ASDoQタグの欠落。
- 6特性の一括無差別ロード、修正時の `snapshot`/`verify` 省略や意味改変、自己修正3周目突入。
- 単体依頼時の DADAプロセス（`SW105`・`[DADA` 進行表示）起動。

## 5. 完了前の自己チェック
- [ ] 思考過程3項目を出力し、単体時は DADAプロセスを起動しなかったか
- [ ] 無断 `--decision1 on` / `/swarm` 拒否と `GEMINI_API_KEY` 非露出を遵守したか
- [ ] `asdoq_lint.py`・`style_check.py` 実行、合格根拠引用、全指摘の形式遵守を確認したか
