---
name: dada-process
description: ソフトウェアの新規開発・機能追加・修正・バグ対応の依頼を受けた時に必ず使用します。要求定義・総合テスト仕様・設計・実装の全工程を、DADAプロセス（Phase 0〜5）に基づきオーケストレーションする標準開発ワークフローです。
---

<!-- UNIT-002 / REQ-002, REQ-006 -->

# DADAプロセス 標準開発ワークフロー

本スキルは DADAプロセス（Phase 1 要求定義 → Phase 2 総合テスト仕様 → Phase 3 設計 → Phase 4 実装・総合テスト報告 → Phase 5 人間評価）全体を制御するオーケストレーターです。共通規則は `.agents/AGENTS.md` に従います。

## 1. 起動時の状態判定と環境分岐（毎回最初に実行）

1. **実在確認と文脈復元**: `docs/process/last_phase_summary.md` を読み、`python tools/dada_verify.py --summary`（または `python tools/dada_check.py all --summary`）で実ファイルを照合する。指示にある参照ファイルが存在しない場合は**推測補完・架空作成せず即座に停止**し、欠損パスを明示報告する。
2. **動作モードと最適化アダプター判定**: 利用可能ツール一覧で `invoke_subagent`、`run_workflow`、`/swarm` の有無を確認する。
   - **ツール自動作成（推奨）**: `invoke_subagent` がある場合は独立サブエージェントへ委譲する（`context-reset` 方式A）。並列・モデル配分が必要な場面では `docs/guidelines/antigravity_adapter.md` をオンデマンドで読む。
   - **人間作成（非対応環境フォールバック）**: `invoke_subagent`・`run_workflow`・`/swarm` 不在の環境（Antigravity IDE / Claude Code / Cursor 等）でもエラー停止せず、承認ゲート型は `context-reset` 方式B、自律型は方式C・順次実行（または標準サブエージェント）へ切り替える。
3. **初回宣言（思考過程3項目＋末尾進行表示）**: 作業開始・完了時に **①現在地 ②判断の根拠 ③次の一手** を出力し、末尾に `[DADA | Phase N: フェーズ名 | 状態: 作成中/レビュー中/承認待ち | 対象: プログラム/エージェント定義 | 承認ゲート型/自律型 | ツール自動/人間作成 | Guided/Autonomous]` を付与する。新規開発の初回応答では4原則・ID体系（`REQ-001` 形式）・承認定義（PO の明示的肯定のみ承認）を簡潔に明示する。

## 2. Phase 0: ルーティング（3つの判定）

1. **開発対象**（`.agents/AGENTS.md` 第6節）: 指示または成果物の性質から「従来型プログラム」または「エージェント定義」を判定する。曖昧・判定不能時は安全側の**従来型プログラム**を仮置きし、Product Owner に確認する。
   - **従来型プログラム時**: `docs/guidelines/agent_def_phase_addon.md`・`docs/guidelines/agent_design_principles.md`・`docs/templates/agent/` は**読み込まない**。
   - **エージェント定義時**: 必ず `docs/guidelines/agent_def_phase_addon.md` と `docs/guidelines/agent_design_principles.md` をオンデマンドで読み込み、以降の工程で `docs/templates/agent/` 配下のひな形と三原則（Simplicity・Transparency・ACI）・5パターン吟味を適用する。
2. **実行モード**: 明示的自律指示（旧称含む）がある場合のみ**自律型**（`docs/process/autoloop_log.md` に開始行追記）。なければ**承認ゲート型**（推定禁止）。
3. **変更スケール**: 3問で **Hotfix** / **Minor** / **Major**（判定不能時は Major）を決定し、根拠とともに報告する。

## 3. 共通フェーズ実行・レビュー手順（Phase 1〜3）

サブエージェントへ渡すのは「適用スキルパス・`docs/process/last_phase_summary.md`・承認済み文書パス・出力先パス・PO指示原文」のみとし、会話履歴要約は渡さない。

1. **作成（ワンパス執筆＋統合検証）**: 作成スキルが `docs/guidelines/asdoq_writing_rules.md` と `JP-Humanizer` 観点で初回執筆し、`python tools/dada_verify.py` を実行する。指摘1件以上なら局所推敲と `style_check.py verify`（上限2回）で解消する。
2. **自己校正レビュー（最大2周）**: レビュースキルが直前検証再利用（`--reuse-cache`）または編集後再検証を行い、`REV101_*.md` に記録する。2周で High 未解消なら3周目に入らず残課題として報告する。
3. **ゲート遷移**:
   - **承認ゲート型（5-A）**: 成果文書パス・機械検証要約・自己レビュー結果・TBD・手順逸脱有無を報告し、Product Owner の明示的承認を待つ（全文再掲禁止）。
   - **自律型（5-B）**: `.agents/AGENTS.md` 第6節の自律ゲート6条件を確認し、`docs/process/autoloop_log.md` へ1行追記して `PROCEED` / `HALT`（停止し選択肢提示）を判定する。
4. **リセット**: ゲート通過直後に `.agents/skills/context-reset/SKILL.md` を実行し、次フェーズへ引き継ぐ。

| Phase | 作成 / レビュースキル | 成果文書 / 記録 | ひな形（従来型 / エージェント定義） |
| :--- | :--- | :--- | :--- |
| **1 要求定義** | `.agents/skills/requirements-engineer/SKILL.md` / `.agents/skills/requirements-reviewer/SKILL.md` | `SW105` / `REV101_Requirements.md` | `.agents/skills/requirements-engineer/references/SW105_skeleton.md` / `docs/templates/agent/phase1_agent_requirements_template.md` |
| **2 テスト仕様** | `.agents/skills/test-engineer/SKILL.md` / `.agents/skills/test-reviewer/SKILL.md` | `SWP6` (1〜4章) / `REV101_Test.md` | `.agents/skills/test-engineer/references/SWP6_skeleton.md` / `docs/templates/agent/phase2_agent_eval_spec_template.md` |
| **3 設計** | `.agents/skills/architect/SKILL.md` / `.agents/skills/architecture-reviewer/SKILL.md` | `SW205` / `REV101_Design.md` | `.agents/skills/architect/references/SW205_skeleton.md` / `docs/templates/agent/phase3_agent_design_template.md` |

- Phase 2 でテスト項目を書けない曖昧要求を検出した場合は推測で埋めず Phase 1 へ差し戻す（ループバック上限2回）。

## 4. Phase 4〜5 の実行

- **Phase 4（実装・総合テスト報告）**: `programmer`（`.agents/skills/programmer/SKILL.md`）が `docs/process/impl_progress.md` に沿って下層から実装・単体テスト（`unit-test-generator`、同一失敗5回停止）を行い、`SWP6` 5〜6章を締結する。並列指示かつ対応環境なら `antigravity_adapter.md` を参照し、非対応環境は順次／標準サブエージェントで実行する。エージェント定義時は `docs/guidelines/agent_def_phase_addon.md` に従い `python tools/agent_def_check.py all --summary` と `docs/process/eval_report.md` を完了する。検証後、`code-reviewer` と `test-reviewer`（Phase 4節）で自己検閲（最大2周）し、ゲートを通過後 `context-reset` で Phase 5 へ渡す。
- **Phase 5（人間評価）**: 実行モードによらず Product Owner が評価する（`docs/process/phase5_evaluation_guide.md`）。`BUG101` 時は Phase 4 へ、要求変更時は Phase 1→2→(3)→4 へ戻る。

## 5. 禁止事項
- 承認ゲート通過前のコード先行作成、認められていないフェーズスキップ。
- 承認や実行モードの推定、自律ゲート条件の緩和、`docs/process/autoloop_log.md` 無記録遷移。
- 従来型プログラム時のエージェント定義指針（`agent_design_principles.md` 等）の不要読込。
- 未指示 `/swarm` 起動、無断 `--decision1 on` 実行、非対応環境でのエラー停止。
- 欠損ファイルの推測補完、架空 ID・仕様の創作、成果物全文のチャット二重出力。

## 6. 完了前のチェックリスト
- [ ] 思考過程3項目と末尾進行表示1行を出力したか
- [ ] Phase 0 判定（開発対象・実行モード・スケール）と環境判定を宣言したか
- [ ] ゲート通過条件・機械検証終了コード0・自己校正上限（2周）を確認したか
- [ ] `context-reset` で `docs/process/last_phase_summary.md` を更新して引き継いだか
