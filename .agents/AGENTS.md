<!-- UNIT-001 / REQ-001 -->
# DADA Process Workspace Rules (ワークスペース憲法)

本ファイルは AI エージェントの最上位ルール（不変条件の正本）である。詳細手順やガイドラインはオンデマンド参照先へ分離し、常時注入サイズを 12,288 bytes 以下に保つ。

## 1. 定義と起動・振り分け

DADA (Document-and-Agent-Driven Agile) プロセスは、Phase 1 要求定義 → Phase 2 総合テスト仕様 → Phase 3 設計 → Phase 4 実装・総合テスト報告 → Phase 5 人間評価で構成する人間と AI の協同開発プロセスである。

- **ソフトウェア開発依頼**: `.agents/skills/dada-process/SKILL.md` を読み込み、Phase 0 の 3 判定（開発対象・実行モード・変更スケール）を実施・宣言する。
- **単体スキル直接利用（DADA プロセスを起動しない）**: 開発工程を伴わない以下の単体依頼や質問応答は、Phase 0〜5 および `[DADA` 進行表示を起動せず対象スキルのみで完結する。
  1. Office 文書・PDF の編集・変換のみ: `.agents/skills/office-document/SKILL.md` / `tools/office_io.py`
  2. 日本語文章の自然化推敲のみ: `.agents/skills/JP-Humanizer/SKILL.md` / `tools/style_check.py`
  3. ASDoQ 品質レビュー・改善のみ: `.agents/skills/asdoq-reviewer/SKILL.md` / `tools/asdoq_lint.py`

## 2. DADAプロセスの4原則（絶対不変条件）

1. **ドキュメント絶対主義 (Single Source of Truth)**: 対応する開発文書（`docs/artifacts/` 配下 `.md`）の更新なしにコード先行で実装・修正してはならない。実ファイルへの確定と、パス・要約のみの報告（二重出力禁止）を徹底する。
2. **承認ゲート**: 承認ゲート型では `SW105`、`SWP6`（1〜4章）、`SW205`、`SWP6`（5〜6章）の完成時に Product Owner の明示的承認を得るまで次工程へ進んではならない。テスト工程は単体と総合のみ（結合テストなし）とし、実施・結果記入は Phase 4 で AI が完了する。
3. **アテンション・リセット**: ゲート通過直後に `.agents/skills/context-reset/SKILL.md` を実行する。次フェーズへ渡してよいのは `docs/process/last_phase_summary.md` と承認済み最新文書パスのみであり、会話履歴の要約を渡してはならない。
4. **役割の純化**: 該当ペルソナスキルを読み込み、役割の範囲内で作業する。作成役が自己承認したり、レビュー役が対象文書を直接書き換えたりしてはならない。

## 3. 不変条件と手順の分離・実行プロファイル

| 層 | 内容 | 扱い |
| :--- | :--- | :--- |
| **不変条件** | 4原則、ID体系、承認定義、禁止事項・完了チェック、機械検証、二重出力禁止 | **常に絶対。省略・緩和禁止** |
| **手順** | 各スキルの作業ステップ順・報告定型文 | 品質の下限足場（目的を上回る手段は可） |

- **実行プロファイル**: 既定は **Guided**（手順順に実行し、迷えば確認）。自律指示時のみ **Autonomous**（不変条件・機械検証を保ち手順を統合可）とし、切替理由と逸脱を 1 行で報告する。

## 4. トレーサビリティID体系・文書管理

| 対象 | ID形式 | 定義元 / 記録先 | 運用規則 |
| :--- | :--- | :--- | :--- |
| 要求 | `REQ-001` 形式 | `docs/artifacts/SW105_ソフトウェア要求仕様書.md` | SW205・SWP6 から必ず参照 |
| テスト項目 | `TC-001` 形式 | `docs/artifacts/SWP6_ソフトウェア総合テスト仕様書・報告書.md` | テストコードのコメントに明記 |
| 設計ユニット | `UNIT-001` 形式 | `docs/artifacts/SW205_ソフトウェアアーキテクチャ設計書.md` | 成果物ヘッダ／冒頭に明記 |
| 評価ケース | `EV-001` 形式 | `SWP6`（エージェント定義時） | `docs/process/eval_report.md` に記録 |
| レビュー指摘 | `R001` 形式 | `docs/artifacts/REV101_Requirements.md` 等（`Test` / `Design`） | `❌ Before`/`✅ After`・`[ASDoQ:特性-副特性]` 必須 |
| バグ | `B001` 形式 | `docs/artifacts/BUG101_バグ管理表.md` | 原因・修正内容を追記し解決済化 |

- **IDは転記・創作禁止**: 元文書を開いて正確にコピーする。架空の ID・ファイル内容を創作してはならない。
- **状態ファイル**: `docs/process/last_phase_summary.md`（引継）、`docs/process/impl_progress.md`（台帳）、`docs/process/check_report.md`（検証）、`docs/process/autoloop_log.md`（自律ログ）、`docs/process/eval_report.md`（評価）、`docs/process/agent_def_check_report.md`（定義検査）。

## 5. 承認定義・透明性・停止条件

- **承認の定義**: Product Owner の明示的な肯定（「承認します」「OK」「次へ進んで」等）のみ。質問・感想・部分同意を承認と推定し先取りしてはならない。
- **思考過程の義務**: 全スキルは開始・完了時に **①現在地 ②判断の根拠 ③次の一手** を出力する。DADA 実行中は全応答末尾に次の進行表示 1 行を出力する（単体スキル直接利用時は出力しない）。
  `[DADA | Phase N: フェーズ名 | 状態: 作成中/レビュー中/承認待ち | 対象: プログラム/エージェント定義 | 承認ゲート型/自律型 | ツール自動/人間作成 | Guided/Autonomous]`
- **自己校正上限**: 作成とレビューの往復は最大 2 周。2 周で未解消の High 指摘は 3 周目に入らず残課題として報告する。

## 6. Phase 0 判定規則（開発対象・スケール・実行モード）

### 開発対象判定（2問）
1. Product Owner が「エージェント定義」「エージェント一式」と明示しているか → Yes なら **エージェント定義**。
2. 最終成果物が AI に読ませる自然言語指示書（スキル・ルール・プロンプト）か → Yes なら確認のうえ **エージェント定義**、No または判定不能時は安全側の **従来型プログラム** を仮置きして確認する。
- **従来型プログラム時はエージェント定義用指針を読み込まない。** エージェント定義時のみ `docs/guidelines/agent_def_phase_addon.md` と `docs/guidelines/agent_design_principles.md` を参照し、三原則（Simplicity・Transparency・ACI）・5パターン吟味・一貫性5項目（単一情報源・定数重複禁止・引数一致・参照実在・終了コード一致）・複数回試行評価を遵守する。

### スケール判定（3問）
1. `SW105` の追加・変更が必要か → 不要なら **Hotfix**（Phase 4→5）。
2. （必要な場合）`SW205` のユニット追加・IF変更・依存変更が必要か → 不要なら **Minor**（Phase 1→2→4→5）。
3. 必要または判定不能なら安全側の **Major**（全 Phase 実行）とし、理由を報告する。

### 実行モードと自律ゲート（既定: 承認ゲート型）
- 起動指示に自律実行（「DADAプロセス自律型」「自律型」「人間の確認を待たずに」、旧称「自律メタLoop型」「自律メタLoopモード」）の明示がある場合のみ **自律型**（Phase 1〜4 承認の事前委譲）。なければ **承認ゲート型**（旧称「対話型」「対話モード」含む）。「要求仕様だけ確認する」時は Phase 1 後のみ人が承認する。**Phase 5 は常に人間が評価し自律化しない。**
- **自律ゲート 6 条件**（全充足時のみ遷移、`docs/process/autoloop_log.md` へ 1 行追記必須）: (1) 自律型明示、(2) `dada_verify.py`（または `dada_check.py`）終了コード `0`、(3) 自己校正 2 周以内で残 High 0 件、(4) 保存済みファイルで完了条件充足、(5) エージェント定義時は評価定義・`eval_report.md` 閾値達成、(6) 下記必須停止条件に非該当。
- **必須停止条件**: 曖昧要求、設計矛盾、自己校正 2 周超過、機械 High 指摘 2 回連続未解消、同一テスト 5 回連続失敗、判定不能、破壊的操作・外部課金・秘密情報操作、スコープ外要求、同一 Phase 2 回ループバック時は即停止し選択肢を報告する。

## 7. 機械検証・外部ガードとガイドライン参照表

- **機械検証の委譲**: 照合・曖昧語・空欄・AI-Slop・図表規則は `python tools/dada_verify.py`（および `dada_check.py` / `agent_def_check.py`）へ委譲する。実行不能時のみ手動走査し未実行を明記する。
- **外部API・秘密情報・並列ガード**: `--decision1` 既定は `off`。未承認 `--decision1 on` や未指示 `/swarm` は拒否し、`GEMINI_API_KEY` を一切出力しない。参照欠損時は即停止し欠損パスを報告する。

| 参照対象 | 用途（オンデマンドで読み込み、常時ロードしない） |
| :--- | :--- |
| `docs/guidelines/dada_document_guidelines.md` | 標準目次構造・執筆/レビュー基準 |
| `docs/guidelines/asdoq_writing_rules.md` | 作成者向け ASDoQ 執筆ルール 12 箇条 |
| `docs/guidelines/asdoq_checklist.md` | レビュー役向け軽量チェックリスト |
| `docs/guidelines/asdoq_model_markdown.md` | 厳密校正指示時のみロードする ASDoQ フル版 |
| `docs/guidelines/agent_def_phase_addon.md` | エージェント定義開発専用の Phase 0〜4 差分手順 |
| `docs/guidelines/agent_design_principles.md` | エージェント定義の三原則・5パターン・評価・ポカヨケ原則 |
| `docs/guidelines/antigravity_adapter.md` | Antigravity 環境向けモデル分担・並列・非対応切替指針 |
| `docs/guidelines/coding_guidelines.md` | Phase 4 実装・テストコード規約 |
| `docs/process/phase5_evaluation_guide.md` | Phase 5 人間評価ガイド |
