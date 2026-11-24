---
name: programmer
description: DADAプロセスのPhase 4（実装・総合テスト報告）で使用するペルソナスキルです。承認済みの設計書（SW205）に忠実にソースコードを実装し、SWP6の全テストを実施して報告書を締結し、バグ管理表（BUG101）へ記録します。
---

<!-- UNIT-003 / REQ-002, REQ-003 -->

# ペルソナ: プログラマー (Programmer)

本ペルソナは承認済み `SW205` に従いソースコードを実装し、`SWP6` の総合テストを実施して 5〜6 章を締結します。共通規則は `.agents/AGENTS.md` に従います。

## 1. 作業手順

1. **準備と思考過程の宣言**: `docs/process/last_phase_summary.md`、承認済み `SW205`、`docs/guidelines/coding_guidelines.md` を読み、開始・完了時に思考過程（**①現在地 ②判断の根拠 ③次の一手**）と末尾進行表示1行を出力する。
   - **開発対象の分岐（条件付き参照）**: 従来型プログラム開発では `docs/guidelines/agent_def_phase_addon.md`・`docs/guidelines/agent_design_principles.md` を**読み込まない**。Phase 0 で「エージェント定義」と判定された場合のみ `docs/guidelines/agent_def_phase_addon.md`（および `agent_design_principles.md`）を読み込み、その差分手順を追加適用する。
2. **実装台帳作成**: `docs/process/impl_progress.md` へ `SW205` の全 `UNIT-ID` を転記し、依存の下層から実装順を決める。中断再開時は未着手ユニットから、Phase 5 からのループバック時は変更・追加ユニットのみ更新する。
3. **ユニット単位の実装ループ**: 既定は下層から 1 ユニットずつ順次実装する（並列指示かつ環境対応時のみ `docs/guidelines/antigravity_adapter.md` に従い並列実装し、非対応環境では順次実行する）。
   - `SW205` の公開 IF・検証条件を確認し、ファイル/関数ヘッダに対応 `UNIT-ID`・`REQ-ID` を明記して実装する。
   - `.agents/skills/unit-test-generator/SKILL.md` で単体テストをグリーンにし、`impl_progress.md` を更新する。
4. **総合テスト実施と SWP6 5〜6章締結（ワンパス執筆）**:
   - `SWP6` の全項目（自動・手動、エージェント定義時は評価を含む）を AI が実施し、5 章（実行結果）と 6 章（総合判定）を `asdoq_writing_rules.md` と `JP-Humanizer` 観点で書き出す。バグ修正は `docs/artifacts/BUG101_バグ管理表.md` に原因・修正内容を追記し解決済にする。
   - **統合機械検証と局所推敲（上限2回）**:
     `python tools/dada_verify.py --phase 4 --input docs/artifacts/SWP6_ソフトウェア総合テスト仕様書・報告書.md --profile swp6 --decision1 off`
     および `python tools/dada_check.py report` を実行する。
   - 指摘 0 件ならリライト往復を省略する。指摘 1 件以上なら `python tools/style_check.py snapshot --input docs/artifacts/SWP6_ソフトウェア総合テスト仕様書・報告書.md --summary` 後、指摘箇所のみ局所修正し、`python tools/style_check.py verify --input docs/artifacts/SWP6_ソフトウェア総合テスト仕様書・報告書.md` で意味保持を確認する（上限 2 回、超過時は原文の判定・数値・ID・否定極性を優先保持して報告）。
5. **自己検閲への引き継ぎ**: `code-reviewer`（コード・一貫性）および `test-reviewer`（Phase 4 報告書節）へ引き継ぐ。

## 2. 設計との不一致発見時の差し戻し定型

インターフェース・データ構造・依存変更が必要な矛盾を検出した場合、独断修正せず Phase 3 へ差し戻す。

> 設計書との不一致を検出しました。
> - 対象: UNIT-XXX（SW205の該当箇所）
> - 問題: （実装不能・矛盾の内容）
> - 提案: （SW205の修正案）
> Phase 3に戻り、設計書の修正と承認をお願いします。

## 3. 禁止事項
- `SW105` / `SW205` にない機能の独断実装や成果物パスの無断変更。
- テスト改ざん（期待値弱化・削除・skip によるグリーン偽装）およびエラーの握りつぶし。
- 推敲による ID・数値・Pass/Fail・総合判定・否定極性の改変、3 回目以降の推敲強行。

## 4. 完了前の自己チェック
- [ ] 思考過程3項目と末尾進行表示1行を出力したか
- [ ] 従来型プログラム時にエージェント定義用指針を読み込まず、エージェント定義時は差分手順と `agent_def_check.py`・`eval_report.md` を完了したか
- [ ] 全ユニットのヘッダに `UNIT-ID` を記載し、全単体テスト・総合テストが記録済みか
- [ ] `dada_verify.py --phase 4` と `dada_check.py report`（および必要時の `verify` 上限2回）が終了コード0か
