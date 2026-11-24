# 実装進捗台帳 (Implementation Progress)

- **対象設計書**: `docs/artifacts/SW205_ソフトウェアアーキテクチャ設計書.md`（版数: 1.0）
- **最終更新日**: 2026-11-24

## 実装順序の方針
依存されている側（下層：`UNIT-008`, `UNIT-009`, `UNIT-001`, `UNIT-006`, `UNIT-007`）から順に実装する。自然言語ユニット（`UNIT-001`〜`UNIT-007`）とプログラムユニット（`UNIT-008`〜`UNIT-010`）は編集ファイルが非重複のため並列実装し、統合検証・単体テスト・評価セットで合流する。

## 進捗表

| UNIT-ID | ユニット名 | 対応要求 | 状態 | 実装ファイル | テスト | 備考 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| UNIT-001 | ワークスペース憲法（軽量版） | REQ-001 | 完了 | `.agents/AGENTS.md` | 合格 | 10,059 B（上限 12,288 B、73.4%削減） |
| UNIT-002 | オーケストレーター・工程制御スキル群 | REQ-002, REQ-006 | 完了 | `.agents/skills/dada-process/SKILL.md` 他2件 | 合格 | 方式A/B/C維持・B001解決済 |
| UNIT-003 | 作成役ペルソナスキル群（ワンパス軽量版） | REQ-002, REQ-003 | 完了 | `.agents/skills/requirements-engineer/SKILL.md` 他5件 | 合格 | ワンパス執筆・局所推敲 |
| UNIT-004 | レビュー役ペルソナスキル群（再利用・省トークン版） | REQ-002, REQ-008 | 完了 | `.agents/skills/requirements-reviewer/SKILL.md` 他3件 | 合格 | `--reuse-cache` 再利用 |
| UNIT-005 | 単体兼用スキル群・ASDoQ専門定義（軽量版） | REQ-003, REQ-005, REQ-008 | 完了 | `.agents/skills/JP-Humanizer/SKILL.md` 他8件 | 合格 | 単体直接起動・APIガード |
| UNIT-006 | エージェント定義差分・共通執筆ガイドライン群 | REQ-001, REQ-002 | 完了 | `docs/guidelines/agent_def_phase_addon.md` 他4件 | 合格 | 差分手順集約 |
| UNIT-007 | Antigravity最適化アダプター層 | REQ-006 | 完了 | `docs/guidelines/antigravity_adapter.md` | 合格 | 移植性分離・B002解決済 |
| UNIT-008 | 統合機械検証CLI | REQ-003, REQ-004, REQ-008 | 完了 | `tools/dada_verify.py` | 合格 | 単一プロセス直交化（5テストPass） |
| UNIT-009 | ベースライン比較ベンチマークツール | REQ-001, REQ-007 | 完了 | `tools/dada_benchmark.py` | 合格 | v6.1.0比較（全指標PASS） |
| UNIT-010 | スキルセット切り出しおよび一貫性チェッカ更新 | REQ-001, REQ-005 | 完了 | `tools/export_skillset.py`, `tools/agent_def_check.py` | 合格 | 4スキルセット整合（4テストPass） |

## SWP6テストの実行状況

| TC-ID | 実行区分 | 実行結果 | 備考 |
| :--- | :--- | :--- | :--- |
| TC-001 | 自動 | Pass | `test_agent_def_check.py` / `10,059 B` 境界内・exit 0 |
| TC-002 | 自動 | Pass | `test_agent_def_check.py` / 12,289 B超過・欠落検出 exit 1 |
| TC-003 | 評価 | Pass | `EV-001` 10/10（100%） |
| TC-004 | 評価 | Pass | `EV-002` 10/10（100%） |
| TC-005 | 評価 | Pass | `EV-003` 10/10（100%） |
| TC-006 | 評価 | Pass | `EV-004` 10/10（100%） |
| TC-007 | 評価 | Pass | `EV-005` 10/10（100%） |
| TC-008 | 自動 | Pass | `test_dada_verify.py` / 意味保持確認 exit 0 |
| TC-009 | 自動 | Pass | `test_dada_verify.py` / 意味破壊検出 exit 1 |
| TC-010 | 評価 | Pass | `EV-006` 10/10（100%） |
| TC-011 | 評価 | Pass | `EV-007` 10/10（100%） |
| TC-012 | 自動 | Pass | `test_dada_verify.py` / 1,000行3秒以内・既定off・直交重複排除 |
| TC-013 | 自動 | Pass | `test_dada_verify.py` / CLI 4回（5回以下）・既存4CLI互換 |
| TC-014 | 自動 | Pass | `test_dada_verify.py` / 異常終了 exit 2・通信なし |
| TC-015 | 自動 | Pass | `test_export_skillset.py` / 4スキルセット切り出し整合 exit 0 |
| TC-016 | 自動 | Pass | `test_export_skillset.py` / ソース欠損時エラー終了 |
| TC-017 | 評価 | Pass | `EV-008` 10/10（100%） |
| TC-018 | 評価 | Pass | `EV-009` 10/10（100%） |
| TC-019 | 評価 | Pass | `EV-010` 5/5（100%） |
| TC-020 | 評価 | Pass | `EV-011` 5/5（100%） |
| TC-021 | 自動 | Pass | `test_dada_benchmark.py` & `dada_benchmark.py` exit 0 |
| TC-022 | 自動 | Pass | `test_dada_benchmark.py` / 境界未達検出 exit 1 |
| TC-023 | 自動 | Pass | `test_dada_benchmark.py` / 不在・欠損検出 exit 2 |
| TC-024 | 評価 | Pass | `EV-012` 10/10（100%） |
| TC-025 | 評価 | Pass | `EV-013` 10/10（100%） |

## 中断・再開の記録
- **次にやること**: `SWP6` 報告書検証・自己校正レビュー完了後、Phase 4 承認ゲート（Gate 5-A）で Product Owner へ報告する。
