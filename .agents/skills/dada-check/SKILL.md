---
name: dada-check
description: 開発文書（SW105/SWP6/SW205）とソースコードの機械的な検証を、統合機械検証CLIおよび決定論的スクリプトへ委譲する手順です。ID対応照合、曖昧語・空欄走査、未実装検出をコマンド実行で行います。
---

<!-- UNIT-002 / REQ-002 -->

# 機械チェックの実行 (DADA Check)

本スキルは ID照合（`REQ`↔`TC`↔`UNIT`）・曖昧語・表空欄・図表規則・AI-Slop・未実装検出を `tools/dada_verify.py` 等へ委譲します。開始・完了時に思考過程（①現在地 ②判断の根拠 ③次の一手）と末尾進行表示1行を出力します。

## 1. 実行手順

### Step 1: コマンド実行
- **基本一括検証**: `python tools/dada_verify.py --phase <1|2|3|4|all> --input <対象パス> --profile <sw105|swp6|sw205|general> --decision1 off`
- **キャッシュ再利用（未編集文書レビュー時）**: `python tools/dada_verify.py --phase <1|2|3|4|all> --reuse-cache --summary`
- **Phase 4 報告書検証**: `python tools/dada_check.py report`
- **エージェント定義検証（該当開発時のみ）**: `python tools/agent_def_check.py all --summary`

※ `--decision1` 既定は `off`。事前承認なく `--decision1 on` を実行してはならない。

### Step 2: 終了コードによる分岐（必須）
要約文面ではなく終了コード（PowerShell `$LASTEXITCODE` / bash `$?`）で判定する。

| 終了コード | 意味 | 対処 |
| :---: | :--- | :--- |
| `0` | High 指摘なし | 内容妥当性検証またはゲート判定へ進む |
| `1` | High 指摘あり | `docs/process/check_report.md` を確認し修正・再実行。同一 High 2回連続未解消時は停止して報告する |
| `2` | 実行エラー | 外部通信・推測補完せず標準エラーを確認し修正。実行不能環境では手動走査へ切替え未実行を明記する |

### Step 3: 内容検証と結果報告
- 機械が検証するのは形式のみ。要求適否・テスト十分性・設計根拠・論理矛盾は AI 自身が判断する。
- エージェント定義時は `SW205` の各 UNIT に `成果物パス` を明記し、単体テストを `tests/` 配下に置き、「評価」区分を `docs/process/eval_report.md` で確認する。
- 報告には `docs/process/check_report.md` のパスと要約1行のみを含め、全文を再掲しない。

## 2. 禁止事項
- 未実行・失敗状態での虚偽「OK」報告、High 指摘の隠蔽、レポート全文のチャット二重出力、無断 `--decision1 on` 実行。

## 3. 完了前の自己チェック
- [ ] 指定フラグと終了コード（0/1/2）を確認し、パスと要約1行のみ報告したか
