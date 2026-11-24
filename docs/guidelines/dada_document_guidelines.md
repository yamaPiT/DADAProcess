<!-- UNIT-006 / REQ-001 -->
---
title: DADAプロセス ドキュメント作成ガイドライン
file_path: docs/guidelines/dada_document_guidelines.md
version: 4.0
date: 2026-11-24
author: Product Owner
description: DADAプロセスにおいてAIエージェントが開発ドキュメント（SW105、SWP6、SW205）を作成・更新するための標準構成ルール。
---

# DADAプロセス ドキュメント作成ガイドライン

## 1. 目的と適用範囲
本ガイドラインは `docs/artifacts/` 配下の開発成果文書（`.md`）の標準目次構成を定める。
1. `SW105`: ソフトウェア要求仕様書（Phase 1）
2. `SWP6`: ソフトウェア総合テスト仕様書・報告書（Phase 2 で1〜4章計画、Phase 4 でAIが5〜6章を追記）
3. `SW205`: ソフトウェアアーキテクチャ設計書（Phase 3）

## 2. 基本ルール
- **追跡可能性**: `REQ-001` ↔ `TC-001` ↔ `UNIT-001` を機械照合できること。
- **Office連携**: 通常は `.md` のみを作成し、Office出力指示時のみ `.agents/skills/office-document/SKILL.md`（`tools/office_io.py`）を使う。
- **ひな形優先**: 新規時は下記ひな形をコピーする（PO指定テンプレート `docs/templates/IEEE29148_2018_SRS.md` 等があれば優先）。
  - **従来型プログラム**: `.agents/skills/requirements-engineer/references/SW105_skeleton.md` / `.agents/skills/test-engineer/references/SWP6_skeleton.md` / `.agents/skills/architect/references/SW205_skeleton.md`
  - **エージェント定義**（詳細は `docs/guidelines/agent_def_phase_addon.md`）: `docs/templates/agent/phase1_agent_requirements_template.md` / `phase2_agent_eval_spec_template.md` / `phase3_agent_design_template.md`

## 3. ドキュメント別 標準目次構造

### 【A】 `SW105`（Phase 1）
- **1. 概要**: 1.1 目的 / 1.2 適用範囲（スコープ内外）/ 1.3 用語定義
- **2. システム全体構成**: 2.1 概要 / 2.2 構成要素（エージェント定義時は 2.3 役割分割・2.4 三原則・2.5 5パターン吟味）
- **3. 制約条件と前提事項**: 3.1 ハードウェア（または実行環境）制約 / 3.2 ソフトウェア環境 / 3.3 準拠規格
- **4. 機能要求**: 4.1 ユースケース / 4.2 機能詳細（`#### REQ-001:` 形式で概要・入出力・異常系・検証条件・優先度。エージェント定義時は `レイヤー` 追加）
- **5. 外部IF要求**: 5.1 UI / 5.2 ハードウェアIF / 5.3 ソフトウェアIF
- **6. 非機能要求**: 6.1 性能 / 6.2 信頼性・安全性 / 6.3 保守性 / 6.4 セキュリティ
- **7. その他・特記事項**: TBD（解消時期・方法併記）と引継事項

### 【B】 `SWP6`（Phase 2 計画 / Phase 4 報告）
- **1. テストの概要と目的**: 1.1 目的 / 1.2 参照 / 1.3 対象範囲
- **2. テスト環境とシステム構成**: 2.1 システム構成 / 2.2 設備・ツール（設計依存は `TBD（Phase 3で確定）`）
- **3. テスト方針**: 3.1 合否判定基準 / 3.2 異常系方針 / 3.3 AI非スクリプト実施項目（エージェント定義時は 3.3 評価方針・3.4 手動項目）
- **4. テストシナリオと項目詳細**: 全 `REQ-ID` に正常系1＋異常系・境界値1以上の表（`テストID`/`対象要件`/`シナリオ`/`前提条件`/`入力データ`/`期待される出力`/`実行区分`）と網羅性確認（エージェント定義時は 4.3 評価セット `EV-001`・ルーブリック）
- **5. テスト実行結果（Phase 4でAI記入）**: 5.1 実行環境 / 5.2 結果詳細 / （5.3 評価集計）
- **6. 総合判定と不具合報告（Phase 4でAI記入）**: 6.1 不具合（`B-ID`）/ 6.2 総合判定（`Pass`/`Fail`）

### 【C】 `SW205`（Phase 3）
- **1. 概要**: 1.1 目的 / 1.2 適用範囲 / 1.3 参照 / 1.4 用語定義
- **2. システム構成**: 2.1 全体構成 / 2.2 主たる要素
- **3. ソフトウェア構成**: 3.1 全体構成（コンポーネント図。エージェント定義時は5パターン・ファイル構成）/ 3.2 機能ユニット（`#### UNIT-001:` 形式で責務・対応要求・公開IF・依存先・検証条件。エージェント定義時は `レイヤー`・`成果物パス`・ポカヨケ）
- **4. 制御方式**: 4.1 メモリ/コンテキスト管理 / 4.2 制御方式（シーケンス図・ループ上限）/ 4.3 性能見積り
- **5. 機能ユニット詳細**（エージェント定義時はACI仕様表）/ **6. データ** / **7. 例外・異常処理**
- **8. その他**: 8.1 ADR（`ADR-001`）/ 8.2 TBD解消表 / 8.3 トレーサビリティ表（`REQ`↔`UNIT`）/ （8.4 ポカヨケ適用表）

## 4. 執筆・検証・自己校正基準
1. **ワンパス執筆**: `docs/guidelines/asdoq_writing_rules.md` と `JP-Humanizer` で執筆し、`python tools/dada_verify.py` を実行する（指摘0件なら再推敲省略、指摘あり時のみ `style_check.py snapshot`→局所修正→`verify` 上限2回）。
2. **自己校正**: 直前検証済み＆未変更なら `--reuse-cache`（または直前レポート参照）で重複実行を省き、`docs/guidelines/asdoq_checklist.md` と `.agents/skills/asdoq-reviewer/SKILL.md`（C1〜C6）で反証レビューし、`REV101_*.md` に記録する。
