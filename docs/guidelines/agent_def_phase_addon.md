<!-- UNIT-006 / REQ-001, REQ-002 -->

# エージェント定義 開発差分ガイドライン（Phase 0〜4）

Phase 0 で「エージェント定義」と判定された場合のみ読み込む差分手順の単一情報源（**従来型プログラム時は読込禁止**）。基礎原則は `docs/guidelines/agent_design_principles.md` 参照。

## Phase 0: ルーティング準備
- `docs/guidelines/agent_design_principles.md` をロードし、`docs/templates/agent/` 使用・三原則（Simplicity・Transparency・ACI）必守・5パターン吟味（採用任意）を宣言する。

## Phase 1: 要求定義（`requirements-engineer` 差分）
- **ひな形**: `docs/templates/agent/phase1_agent_requirements_template.md`。自然言語（スキル・ルール・知識）とプログラム（ツール）の二重構造を明記し、対象製品・ツール・自律範囲・揺れ許容・役割分割を確認する。
- **三原則と5パターン（先行・省略禁止）**: (1) **Simplicity（2.3節）**: 第2.5節の5問で役割分割と不採用理由を記載、(2) **Transparency/ACI（2.4節）**: 思考過程出力と `description`・手順・出力形式を要求化、(3) **5パターン（2.5節）**: Prompt Chaining / Routing / Parallelization / Orchestrator-Workers / Evaluator-Optimizer 全5件の採否と理由を記載（空欄禁止）。
- **レイヤー・検証・異常系**: 第3.2節の3問で各REQに `レイヤー` を付し、自然言語は「**必須要素・禁止要素・試行回数（>=2）・合格率閾値**」で検証条件を書く。異常系に幻覚・逸脱・指示漏れ・参照欠損を入れ、6.2節に確率的許容範囲を数値記載する。

## Phase 2: 総合テスト仕様（`test-engineer` 差分）
- **ひな形**: `docs/templates/agent/phase2_agent_eval_spec_template.md`。プログラムは「自動」、自然言語は「評価」に区分し、4.3節へ `EV-001` 形式（入力プロンプト全文・必須/禁止要素・判定方法［決定論優先］・試行回数［Must=10/Should=5/Could=3、1回禁止］・合格基準）を定義する。ルーブリックは0/1観点で全1点合格とし、欠損パス・矛盾・幻覚・役割逸脱の異常系を含める。

## Phase 3: アーキテクチャ設計（`architect` 差分）
- **ひな形**: `docs/templates/agent/phase3_agent_design_template.md`。SW105 2.5節を3.1節へ転記確定し、1役割=1スキル=1UNIT（Generator/Evaluator分離、ループ管理はOrchestrator）で全UNITに `レイヤー`・`成果物パス` を明記し、`description` 重複を防ぐ。
- 自然言語UNIT公開IF（発動条件・入出力・思考過程・出力形式・ツール）、プログラムUNIT 5章ACI仕様表（スキル手順とコマンド・終了コード0/1/2一致）、4.1節読込制限、4.2節ループ上限、8.4節ポカヨケ8基準、7章例外を記載する。

## Phase 4: 実装・評価（`programmer` / `code-reviewer` 差分）
- `成果物パス` 通りに生成し冒頭/ヘッダに `UNIT-ID` を記載、単体テストは `tests/` 配下へ置く。
- 憲法第6節の一貫性5項目と `python tools/agent_def_check.py all --summary`（終了コード0）を確認する。
- 全 `EV-ID` を定義回数試行し（独立会話採点、1回試行・閾値緩和禁止）、`docs/process/eval_report.md` と `SWP6` 5.3節へ記録し、ゲート報告に一貫性・評価の2行を追加する。
