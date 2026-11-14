# Phase 4 実装・テスト進捗台帳 (Implementation Progress)

- **最終更新日時**: 2026-11-13
- **対象設計書**: `docs/artifacts/SW205_ソフトウェアアーキテクチャ設計書.md`（版数 1.2）
- **対象テスト仕様書**: `docs/artifacts/SWP6_ソフトウェア総合テスト仕様書・報告書.md`（版数 1.1）

## 1. ユニット実装進捗（SW205 版数 1.2 の全UNIT-ID）

**表1：設計ユニット（UNIT-001〜UNIT-007）実装進捗表**

| UNIT-ID | ユニット名 | レイヤー | 成果物パス | 状態 | 単体検証結果 | 備考 |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| `UNIT-001` | 拡張違反例辞書・企業カスタム辞書管理モジュール | プログラム | `tools/asdoq_dictionary.json`, `tools/asdoq_lint.py` | 実装完了 | Pass (`TC-001`〜`003`) | v1.2.0 / 86ルール / `[ASDoQ:特性-副特性]` / 旧表記拒否 |
| `UNIT-002` | Layer 0 NLP形態素解析・図表検査・構造クロスリファレンス抽出エンジン | プログラム | `tools/asdoq_lint.py` | 実装完了 | Pass (`TC-004`〜`007`) | Mermaid 10ノード上限・`[接続N]`・境界付き図表・テンプレート語マスク |
| `UNIT-003` | Layer 1 Google `gemini-decision-1` 判定・透過フォールバック・CLIモジュール | プログラム | `tools/asdoq_lint.py` | 実装完了 | Pass (`TC-008`〜`012`) | `v1beta/decisions`・1,000問分割・0問スキップ・実API実測済 (`total_output_tokens=0`) |
| `UNIT-004` | ASDoQ 6大品質特性別 専門レビュアー定義群 | 自然言語 | `.agents/skills/asdoq-reviewer/references/C1_purpose_reviewer.md`〜`C6_conformance_reviewer.md` | 実装完了 | Pass (`TC-013`) | 6ファイル各72〜76行(<=200)、[ASDoQ:特性-副特性]、図/Humanizer対応 |
| `UNIT-005` | 単体レビュー調整役・意味保持修正スキル（`asdoq-reviewer`） | 自然言語 | `.agents/skills/asdoq-reviewer/SKILL.md` | 実装完了 | Pass (`EV-004`〜`008`: 25/25) | `--decision1 off` 既定・API確認義務・`/swarm`アダプター・図分割/接続/意味保持 |
| `UNIT-006` | DADA統合定義群（憲法・全工程スキル・ひな形・ガイドライン・帳票） | 自然言語 | `.agents/AGENTS.md`, 各DADAスキル, `docs/guidelines/*`（副次: スケルトン・ひな形・`REV101`） | 実装完了 | Pass (`TC-019`) | 全14主要ファイルに`UNIT-006`タグ付与、旧語句0件、`agent_def_check.py unit/skill/command` OK |
| `UNIT-007` | スキルセット切り出し機構・配布設定・リポジトリ利用案内 | プログラム / 自然言語 | `tools/export_skillset.py`, `README.md`, `.env.example`, `.gitignore` | 実装完了 | Pass (`TC-021`, `TC-022`) | 5セット/README/env出力、Tips 16-17、SW105表9公式URL、旧語句0件 |

- **次にやること**: `SWP6`（5〜6章）の記入・`JP-Humanizer` 適用および Phase 4 自己校正（`code-reviewer` / `test-reviewer`）を完了し、承認ゲートで停止する。

## 2. 総合テスト実施進捗（SWP6 版数 1.1 の全TC-ID）

**表2：総合テスト項目（TC-001〜TC-023）実施進捗表**

| TC-ID | 対応REQ-ID | 実行区分 | 検証方法 / テストメソッド・評価ID | 判定 | 備考 |
| :--- | :--- | :---: | :--- | :---: | :--- |
| `TC-001` | `REQ-001` | 自動 | `tests/test_asdoq_reviewer.py::test_tc001_dictionary_80_vs_79_boundary_and_canonical_names` | Pass | 86件/8カテゴリ/79件境界/正準6特性名検証済 |
| `TC-002` | `REQ-001` | 自動 | `tests/test_asdoq_reviewer.py::test_tc002_custom_dictionary_merge_and_whitelist_masking` | Pass | 企業NG/OK/無効化/規範ルール統合検証済 |
| `TC-003` | `REQ-001` | 自動 | `tests/test_asdoq_reviewer.py::test_tc003_dictionary_error_handling_and_cli_exit2` | Pass | 不在/構文不正/必須キー欠落終了コード2 |
| `TC-004` | `REQ-002` | 自動 | `tests/test_asdoq_reviewer.py::test_tc004_layer0_categories_crossref_and_exit_codes` | Pass | 全8カテゴリ/構造クロス4項目/テンプレート語除外 |
| `TC-005` | `REQ-002` | 自動 | `tests/test_asdoq_reviewer.py::test_tc005_mermaid_10_vs_11_nodes_connection_pairs_and_captions` | Pass | Mermaid 10/11ノード/`[接続N]`/図表境界/図下表上 |
| `TC-006` | `REQ-002` | 自動 | `tests/test_asdoq_reviewer.py::test_tc006_slice_compression_max_items_25_26_and_latency` | Pass | 圧縮率50%以下/25-26件制限/0.1s未満(<3.0s) |
| `TC-007` | `REQ-002` | 自動 | `tests/test_asdoq_reviewer.py::test_tc007_missing_empty_file_and_janome_stdlib_fallback` | Pass | 不在/空ファイル終了コード2/stdlibフォールバック |
| `TC-008` | `REQ-003` | 自動 | `tests/test_asdoq_reviewer.py::test_tc008_decision1_mock_noul_choice_score_and_threshold_boundary` | Pass | `MockDecision1Client`/閾値0.30保持・0.29棄却 |
| `TC-009` | `REQ-003` | 自動 | `tests/test_asdoq_reviewer.py::test_tc009_default_decision1_off_offline_fallback` | Pass | 既定 `--decision1 off` 外部通信0回 |
| `TC-010` | `REQ-003` | 自動 | `tests/test_asdoq_reviewer.py::test_tc010_key_priority_1000_chunking_and_zero_question_skip` | Pass | キー順/999+3=1002問分割/0問スキップ |
| `TC-011` | `REQ-003` | 自動 | `tests/test_asdoq_reviewer.py::test_tc011_missing_key_deprecated_flag_threshold_range_retries_and_clean_codebase` | Pass | キー未設定/旧CLI廃止/2回リトライ/非露出/旧語句0件 |
| `TC-012` | `REQ-003` | 手動 | AIによる実機 `.env.local` `--decision1 on` 実行 | Pass | `on (api)`, calls=1, in=2744, out=0, elapsed=0.5641s, 0問スキップ確認 |
| `TC-013` | `REQ-004` | 自動 | `tests/test_asdoq_reviewer.py::test_tc013_specialist_definitions_6_files_and_200_line_boundary` | Pass | 6ファイル実在/<=200行(201境界検出力含む)/6要素/旧表記・`/swarm` 0件 |
| `TC-014` | `REQ-004` | 評価 | `docs/process/eval_report.md` (`EV-001`, `EV-002`) | Pass | `EV-001` 5/5 (100%) / `EV-002` 5/5 (100%) |
| `TC-015` | `REQ-004` | 評価 | `docs/process/eval_report.md` (`EV-003`) | Pass | `EV-003` 5/5 (100%) |
| `TC-016` | `REQ-005` | 評価 | `docs/process/eval_report.md` (`EV-004`, `EV-005`) | Pass | `EV-004` 5/5 (100%) / `EV-005` 5/5 (100%) |
| `TC-017` | `REQ-005` | 評価 | `docs/process/eval_report.md` (`EV-006`) | Pass | `EV-006` 5/5 (100%, 実API ON `calls=1, out=0`) |
| `TC-018` | `REQ-005` | 評価 | `docs/process/eval_report.md` (`EV-007`, `EV-008`) | Pass | `EV-007` 5/5 (100%) / `EV-008` 5/5 (100%, `B006`修正後) |
| `TC-019` | `REQ-006` | 自動 | `tests/test_asdoq_reviewer.py::test_tc019_unit006_cross_consistency_and_no_legacy_terms` & `agent_def_check.py` | Pass | 主要14ファイルタグ・旧語句0件・`unit`/`skill`/`command` 全通過 |
| `TC-020` | `REQ-006` | 評価 | `docs/process/eval_report.md` (`EV-009`) | Pass | `EV-009` 5/5 (100%, `B006`修正後) |
| `TC-021` | `REQ-007` | 自動 | `tests/test_asdoq_reviewer.py::test_tc021_export_skillset_readme_env_and_clean_terms` | Pass | 切り出し・`.env.example`・`.gitignore`・両`README`・Tips 16-17・旧語句0件 |
| `TC-022` | `REQ-007` | 自動 | `tests/test_asdoq_reviewer.py::test_tc022_export_skillset_error_exit_codes` | Pass | 未定義セット名終了コード2・必須ファイル欠損終了コード1 |
| `TC-023` | `REQ-007` | 評価 | `docs/process/eval_report.md` (`EV-010`) | Pass | `EV-010` 3/3 (100%, 決定論的アサーション項目2〜5) |
