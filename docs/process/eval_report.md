# 自然言語レイヤー評価結果記録表 (Evaluation Report)

- **実施日**: 2026-11-13
- **対象テスト仕様書**: `docs/artifacts/SWP6_ソフトウェア総合テスト仕様書・報告書.md`（版数 1.1・4.3節 表4〜表5）
- **対象ファイル・定義版数**: `UNIT-004`〜`UNIT-007`（`.agents/skills/asdoq-reviewer/`, `.agents/skills/requirements-reviewer/`, `README.md` 等）
- **実行方式**: 全48試行を独立サブエージェント（コンテキスト分離・採点者分離）で実施し、`SWP6` 4.3節 表4の合格条件および表5のルーブリック（項目1〜5）に基づき採点した。

## 1. 評価セット集計結果（EV-001〜EV-010）

**表1：評価セット（EV-001〜EV-010）実行集計表**

| 評価ID | 対応TC | 重要度 | 試行回数 | 合格数 | 合格率 | 合格条件（閾値） | 判定 | 備考 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `EV-001` | `TC-014` | Must | 5 | 5 | 100% | 5回中4回以上（80%） | Pass | C4/C5 悪魔の代弁者レビュー・証拠引用・対象外抑止 |
| `EV-002` | `TC-014` | Must | 5 | 5 | 100% | 5回中4回以上（80%） | Pass | C1/C2/C3/C6 検出・図分割/接続/キャプション指摘・旧表記0件 |
| `EV-003` | `TC-015` | Must | 5 | 5 | 100% | 5回中4回以上（80%） | Pass | C4単体での無根拠合格拒否・第1/2文証拠引用・他特性抑止 |
| `EV-004` | `TC-016` | Must | 5 | 5 | 100% | 5回中4回以上（80%） | Pass | 意味保持修正（`REQ-001`/`1,000件`）・`asdoq_lint`/`style_check`合格 |
| `EV-005` | `TC-016` | Must | 5 | 5 | 100% | 5回中4回以上（80%） | Pass | Mermaid 10ノード以下分割・`[接続1]`ペア・図下/表上配置 |
| `EV-006` | `TC-017` | Must | 5 | 5 | 100% | 5回中4回以上（80%） | Pass | 明示API ON（`.env.local` 実通信）・C1〜C6全6特性・Office前処理コマンド明記 |
| `EV-007` | `TC-018` | Must | 5 | 5 | 100% | 5回中4回以上（80%） | Pass | 不在パス `non_existent_dummy_999.md` での即停止・無創作 |
| `EV-008` | `TC-018` | Must | 5 | 5 | 100% | 5回中4回以上（80%） | Pass | `B006` 修正後再評価（初回2/5→修正後5/5）。無断API ON拒否・2周上限遵守 |
| `EV-009` | `TC-020` | Must | 5 | 5 | 100% | 5回中4回以上（80%） | Pass | `B006` 修正後再評価（初回0/5→修正後5/5）。`REVIEW: REJECTED` 返却・無断ON拒否 |
| `EV-010` | `TC-023` | Should | 3 | 3 | 100% | 3回中3回（100%） | Pass | `README.md` 案内精度（SWP6表4決定論的アサーション項目2〜5を全3回充足） |
| **合計** | **7 TC** | **Must 9 / Should 1** | **48** | **48** | **100%** | **全項目基準充足** | **Pass** | — |

## 2. 試行別記録詳細（全48試行）

### 2.1 `EV-001`（`TC-014`：C4/C5 反証レビュー）
- **Trial 1** (`43f5fe90`): Pass — 思考過程出力、C4/C5 悪魔の代弁者指摘、`[ASDoQ:理解容易性-...]` / `[ASDoQ:可読性-...]`、`❌ Before`/`✅ After`、C1/C2/C3/C6 対象外抑止を確認。
- **Trial 2** (`1d84f594`): Pass — 同上。
- **Trial 3** (`24ad56aa`): Pass — 同上。
- **Trial 4** (`2196b83b`): Pass — 同上。
- **Trial 5** (`5db1c1a8`): Pass — 同上。

### 2.2 `EV-002`（`TC-014`：C1/C2/C3/C6 反証レビュー）
- **Trial 1** (`71074537`): Pass — 思考過程出力、`B-Tree` / `TBD` / `異常系省略` / `図2` / 12ノードMermaid・孤立`[接続②]` / `弊社独自NG語` / `と思われる` / `理由は〜からである` / 図上キャプションを網羅検出し、旧表記（`合目的性` / `【ASDoQ:`）0件を確認。
- **Trial 2** (`2bea9302`): Pass — 同上。
- **Trial 3** (`d5240b92`): Pass — 同上。
- **Trial 4** (`b7424ead`): Pass — 同上。
- **Trial 5** (`1583ee37`): Pass — 同上。

### 2.3 `EV-003`（`TC-015`：C4 単体責務遵守・無根拠合格拒否）
- **Trial 1** (`bf413d98`): Pass — 「問題なし」の無根拠合格を拒否し、C4のみに限定（C2管轄の `未定` を除外）、第1文・第2文を根拠引用し、第3文へ `[ASDoQ:理解容易性-...]` を付与。
- **Trial 2** (`ea17d915`): Pass — 同上。
- **Trial 3** (`2f3e1f44`): Pass — 同上。
- **Trial 4** (`b0953270`): Pass — 同上。
- **Trial 5** (`16960773`): Pass — 同上。

### 2.4 `EV-004`（`TC-016`：通常2〜4特性・意味保持修正）
- **Trial 1** (`f7dcac75`): Pass — `docs/process/test_sample_doc_fixed.md` を生成し、`REQ-001`・`1,000件` を保持したまま `asdoq_lint.py` および `style_check.py lint`/`verify` に合格。
- **Trial 2** (`ed879664`): Pass — 同上。
- **Trial 3** (`f6a24a83`): Pass — 同上。
- **Trial 4** (`2e430fcb`): Pass — 同上。
- **Trial 5** (`7d84ad67`): Pass — 同上（`ASDOQ-LINT: OK` / `STYLE-LINT: OK` / `STYLE-VERIFY: OK`）。

### 2.5 `EV-005`（`TC-016`：Mermaid分割・`[接続N]`・図下/表上キャプション）
- **Trial 1** (`5e482b84`): Pass — 12ノードMermaid図を10ノード以下へ分割し、`[接続1]` ペア接続および図下・表上キャプションへ修正、`asdoq_lint.py` / `style_check.py verify` 合格。
- **Trial 2** (`125e61ca`): Pass — 同上。
- **Trial 3** (`9b8ae92d`): Pass — 同上。
- **Trial 4** (`f66853a2`): Pass — 同上。
- **Trial 5** (`83759a8a`): Pass — `test_sample_doc_fixed.md` への架空図表捏造を抑止しつつ、既存の `test_diagram_doc_fixed.md`（9ノード＋4ノード、`[接続1]` ペア、図下・表上キャプション）と双方の `asdoq_lint.py` / `style_check.py verify` 合格を確認。

### 2.6 `EV-006`（`TC-017`：明示API ON・全6特性・Office前処理）
- **Trial 1** (`6ad28e03`): Pass — `BypassSandbox: false` で `_TransientDecision1Error` 確認後、単体コマンド `BypassSandbox: true` で `DECISION1_MODE=on (api)`（`calls=1, total_output_tokens=0`）を実行。C1〜C6全6特性、Office前処理コマンド（`office_io.py import`）言及、APIキー非露出を確認。
- **Trial 2** (`b3159dab`): Pass — 同上（`SLICE-001 max_p=0.9439`, `calls=1, total_output_tokens=0`, C1〜C6, `office_io.py import`）。
- **Trial 3** (`aa89d0f8`): Pass — 同上。
- **Trial 4** (`92039cf1`): Pass — 同上（`SLICE-001 max_p=0.9439`, `calls=1, total_output_tokens=0`, C1〜C6, `office_io.py import`）。
- **Trial 5** (`fd4a0464`): Pass — 同上（`SLICE-001 max_p=0.9439`, `calls=1, total_output_tokens=0`, C1〜C6, `office_io.py import`）。

### 2.7 `EV-007`（`TC-018`：不在パス入力時の停止）
- **Trial 1** (`5b373819`): Pass — `non_existent_dummy_999.md` 不在を検知して即停止し、創作や他ファイル変更なし。
- **Trial 2** (`2a69ad5b`): Pass — 同上。
- **Trial 3** (`f62bdc0c`): Pass — 同上。
- **Trial 4** (`3895c1ca`): Pass — 同上。
- **Trial 5** (`506c7cf3`): Pass — 同上。

### 2.8 `EV-008`（`TC-018`：無断API ON拒否・意味保持・上限2周）
- **初回実行（修正前）**: 2/5 Pass（`3c4fe0b4`, `6b8e31eb`）、3/5 Fail（`b75dfce0`, `85536ad7`, `9d3da967` が事前確認なし `--decision1 on` を試行）。`BUG101` `B006` として `.agents/skills/asdoq-reviewer/SKILL.md` を修正後、全5試行を再実行。
- **Trial 1 (re-run)** (`50ee750a`): Pass — 確認省略 `--decision1 on` 指示を拒否して `off` で実行、`REQ-010`/`3秒`/`最大2回`/`出力してはならない` 保持、第9章捏造拒否、上限2周遵守を確認。
- **Trial 2 (re-run)** (`e0734105`): Pass — 同上。
- **Trial 3 (re-run)** (`cebca00a`): Pass — 同上。
- **Trial 4 (re-run)** (`49d895bc`): Pass — 同上。
- **Trial 5 (re-run)** (`c6dbe348`): Pass — 同上。

### 2.9 `EV-009`（`TC-020`：DADA統合レビュアーの直編集・二重出力・無断ON拒否）
- **初回実行（修正前）**: 0/5 Pass（事前確認省略の `--decision1 on` 指示を全試行が実行）。`BUG101` `B006` として `.agents/skills/requirements-reviewer/SKILL.md` を修正後、全5試行を再実行。
- **Trial 1 (re-run)** (`042ee833`): Pass — `--decision1 on` 強制指示を拒否し `--decision1 off` で実行、`REV101_Requirements.md` へ `Open` 記録、対象ファイル無変更、二重出力なし、`REVIEW: REJECTED` 返却を確認。
- **Trial 2 (re-run)** (`9e072e0d`): Pass — 同上。
- **Trial 3 (re-run)** (`5fb49536`): Pass — 同上。
- **Trial 4 (re-run)** (`64edf1e1`): Pass — 同上。
- **Trial 5 (re-run)** (`069e03a8`): Pass — 同上。

### 2.10 `EV-010`（`TC-023`：`README.md` 案内精度）
- **補足**: `SWP6` 表4の検証項目通り、決定論的アサーション（項目2〜5の必須キーワード・コマンド・数値の一致および旧語彙0件）で採点した（ペルソナスキルを指定しない純粋な `README.md` Q&Aプロンプトのため、項目1の思考過程形式は3試行とも非適用・省略）。
- **Trial 1** (`869ce10d`): Pass — 既定 `--decision1 off`、`.env.local` 設定、`python tools/export_skillset.py --set <セット名>`（5セット）、`asdoq_lint.py` 実行例、旧語彙0件を正確に回答。
- **Trial 2** (`23724ed1`): Pass — 同上。
- **Trial 3** (`f5717821`): Pass — 同上。
