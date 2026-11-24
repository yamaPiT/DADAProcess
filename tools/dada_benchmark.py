#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル名：tools/dada_benchmark.py
バージョン番号：1.0.0
作成日：2026-11-24
プログラマ名：DADA Programmer Agent
ファイルの概要：
    DADAプロセス v7.0 のベースライン比較ベンチマークツール（UNIT-009）。
    内蔵の v6.1.0 ベースライン実測値（または外部 JSON）と指定ルート配下の実ファイルを比較し、
    憲法サイズ（12,288 bytes 以下）、主要5フェーズの読込削減率（50.0% 以上）、
    および標準ワークフローのCLI検証回数（5回以下）の達成判定を行う。
対応機能ID（トレーサビリティ）：
    UNIT-009 (REQ-001, REQ-007)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 定数定義（データ定義コメント付き）
# ---------------------------------------------------------------------------

# v6.1.0 (main ac2bf27) ベースライン実測値定数（SW205 4.3節 表6・8.1節 ADR-004 準拠）
BASELINE_V6_1_0: Dict[str, int] = {
    "agents_md_bytes": 37876,
    "phase1_prog_write": 126875,
    "phase1_prog_review": 119264,
    "phase1_agent_write": 174335,
    "phase3_prog_write": 129449,
    "phase4_prog_write": 117432,
    "cli_checks_per_phase": 10,
}

# 各目標指標の合否判定閾値
MAX_AGENTS_MD_BYTES = 12288
MIN_REDUCTION_PCT = 50.0
MAX_CLI_CHECKS_PER_PHASE = 5

# ワークスペース憲法の相対パス
AGENTS_MD_REL = ".agents/AGENTS.md"

# フェーズ別規定読込ファイルセット定義（SW205 8.1節 ADR-004 準拠）
PHASE_READ_SETS: Dict[str, Tuple[str, ...]] = {
    "phase1_prog_write": (
        ".agents/AGENTS.md",
        ".agents/skills/dada-process/SKILL.md",
        ".agents/skills/requirements-engineer/SKILL.md",
        ".agents/skills/requirements-engineer/references/SW105_skeleton.md",
        ".agents/skills/document-writer/SKILL.md",
        "docs/guidelines/asdoq_writing_rules.md",
        ".agents/skills/JP-Humanizer/SKILL.md",
    ),
    "phase1_prog_review": (
        ".agents/AGENTS.md",
        ".agents/skills/requirements-reviewer/SKILL.md",
        "docs/guidelines/asdoq_checklist.md",
        ".agents/skills/asdoq-reviewer/SKILL.md",
        ".agents/skills/asdoq-reviewer/references/C1_purpose_reviewer.md",
        ".agents/skills/asdoq-reviewer/references/C3_consistency_reviewer.md",
        ".agents/skills/asdoq-reviewer/references/C4_understandability_reviewer.md",
        ".agents/skills/asdoq-reviewer/references/C5_readability_reviewer.md",
        ".agents/skills/JP-Humanizer/SKILL.md",
    ),
    "phase1_agent_write": (
        ".agents/AGENTS.md",
        ".agents/skills/dada-process/SKILL.md",
        ".agents/skills/requirements-engineer/SKILL.md",
        ".agents/skills/document-writer/SKILL.md",
        "docs/guidelines/asdoq_writing_rules.md",
        ".agents/skills/JP-Humanizer/SKILL.md",
        "docs/templates/agent/phase1_agent_requirements_template.md",
        "docs/guidelines/agent_def_phase_addon.md",
        "docs/guidelines/agent_design_principles.md",
    ),
    "phase3_prog_write": (
        ".agents/AGENTS.md",
        ".agents/skills/dada-process/SKILL.md",
        ".agents/skills/architect/SKILL.md",
        ".agents/skills/architect/references/SW205_skeleton.md",
        ".agents/skills/document-writer/SKILL.md",
        "docs/guidelines/asdoq_writing_rules.md",
        ".agents/skills/JP-Humanizer/SKILL.md",
    ),
    "phase4_prog_write": (
        ".agents/AGENTS.md",
        ".agents/skills/dada-process/SKILL.md",
        ".agents/skills/programmer/SKILL.md",
        ".agents/skills/unit-test-generator/SKILL.md",
        "docs/guidelines/coding_guidelines.md",
        ".agents/skills/JP-Humanizer/SKILL.md",
    ),
}

# CLI 検証コマンド行を計数する対象ファイル（SW205 5.2節 表8・ADR-004 準拠）
CLI_COUNT_TARGET_FILES: Tuple[str, ...] = (
    ".agents/skills/requirements-engineer/SKILL.md",
    ".agents/skills/requirements-reviewer/SKILL.md",
)

# 検証コマンド行検出用の正規表現
CLI_CMD_LINE_RE = re.compile(r"python(?:3)?\s+tools/[\w.-]+\.py")

# 指標キーから表示ラベルへのマッピング
METRIC_LABELS: Dict[str, str] = {
    "agents_md_bytes": ".agents/AGENTS.md サイズ",
    "phase1_prog_write": "Phase 1 執筆読込合計（従来型）",
    "phase1_prog_review": "Phase 1 レビュー読込合計（従来型）",
    "phase1_agent_write": "Phase 1 執筆読込合計（エージェント）",
    "phase3_prog_write": "Phase 3 執筆読込合計（従来型）",
    "phase4_prog_write": "Phase 4 執筆読込合計（従来型）",
    "cli_checks_per_phase": "1フェーズのCLI検証回数",
}


# ---------------------------------------------------------------------------
# 例外定義
# ---------------------------------------------------------------------------

class BenchmarkMeasurementError(Exception):
    """計測ルート不在・必須ファイル欠損・不正ベースラインJSONを表す例外。"""


# ---------------------------------------------------------------------------
# 計測・比較ロジック
# ---------------------------------------------------------------------------

def load_baseline(baseline_arg: str) -> Dict[str, int]:
    """
    関数名：load_baseline
    戻り値：ベースライン実測値辞書（7指標）
    引数：baseline_arg (str) - 'v6.1.0' または JSON ファイルパス
    関数の概要：内蔵の v6.1.0 ベースラインまたは外部JSONファイルから基準値をロードする。
    対応機能ID（トレーサビリティ）：UNIT-009 (REQ-007)
    """
    if baseline_arg == "v6.1.0":
        return dict(BASELINE_V6_1_0)

    b_path = Path(baseline_arg)
    if not b_path.is_file():
        raise BenchmarkMeasurementError(f"ベースラインJSONファイルが見つかりません: {b_path}")
    try:
        parsed = json.loads(b_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise BenchmarkMeasurementError(f"ベースラインJSONの解析に失敗しました: {exc}") from exc

    if not isinstance(parsed, dict):
        raise BenchmarkMeasurementError("ベースラインJSONのルートはオブジェクトである必要があります。")

    result: Dict[str, int] = {}
    for key in BASELINE_V6_1_0:
        if key not in parsed:
            raise BenchmarkMeasurementError(f"ベースラインJSONに必須キー '{key}' が不足しています。")
        result[key] = int(parsed[key])
    return result


def collect_required_paths() -> List[str]:
    """
    関数名：collect_required_paths
    戻り値：計測に必須となるリポジトリ相対パスの重複なしソート済みリスト
    引数：なし
    関数の概要：憲法、全5フェーズ読込セット、CLI計数対象ファイルの全パスを集約する。
    対応機能ID（トレーサビリティ）：UNIT-009 (REQ-007)
    """
    paths = {AGENTS_MD_REL}
    for file_list in PHASE_READ_SETS.values():
        paths.update(file_list)
    paths.update(CLI_COUNT_TARGET_FILES)
    return sorted(paths)


def measure_workspace(root: Path, baseline: Dict[str, int]) -> Dict[str, Any]:
    """
    関数名：measure_workspace
    戻り値：全7指標の実測値・削減率・合否・未達項目一覧を含む計測結果辞書
    引数：root (Path) - 計測対象リポジトリルート, baseline (Dict[str, int]) - 比較基準値辞書
    関数の概要：
        指定ルート配下の実ファイルUTF-8バイト数およびCLI検証コマンド行数を計測し、
        目標閾値（憲法<=12,288B, 5フェーズ削減率>=50.0%, CLI<=5回）と照合する。
    対応機能ID（トレーサビリティ）：UNIT-009 (REQ-001, REQ-007)
    """
    if not root.is_dir():
        raise BenchmarkMeasurementError(f"指定されたルートディレクトリが存在しません: {root}")

    # 1. 必須計測ファイルの存在確認（欠損時は欠落パス一覧をまとめて送出）
    required_paths = collect_required_paths()
    missing_paths = [rel_p for rel_p in required_paths if not (root / rel_p).is_file()]
    if missing_paths:
        raise BenchmarkMeasurementError(
            "必須計測ファイルが欠損しています:\n" + "\n".join(f"  - {p}" for p in missing_paths)
        )

    # 2. 各ファイルのUTF-8バイト数計測
    file_sizes: Dict[str, int] = {}
    for rel_p in required_paths:
        file_sizes[rel_p] = (root / rel_p).stat().st_size

    # 3. CLI 検証コマンド行の正規表現計数
    cli_count = 0
    cli_details: Dict[str, int] = {}
    for rel_p in CLI_COUNT_TARGET_FILES:
        content = (root / rel_p).read_text(encoding="utf-8-sig", errors="replace")
        matched_lines = sum(1 for ln in content.splitlines() if CLI_CMD_LINE_RE.search(ln))
        cli_details[rel_p] = matched_lines
        cli_count += matched_lines

    # 4. 7指標の算出と目標判定
    metrics: List[Dict[str, Any]] = []
    failed_items: List[Dict[str, Any]] = []

    # 4a. .agents/AGENTS.md サイズ
    agents_bytes = file_sizes[AGENTS_MD_REL]
    agents_base = baseline["agents_md_bytes"]
    agents_red = round((agents_base - agents_bytes) / max(1, agents_base) * 100.0, 2)
    agents_ok = agents_bytes <= MAX_AGENTS_MD_BYTES
    m_agents = {
        "key": "agents_md_bytes",
        "label": METRIC_LABELS["agents_md_bytes"],
        "baseline": agents_base,
        "actual": agents_bytes,
        "unit": "B",
        "reduction_pct": agents_red,
        "threshold": f"<= {MAX_AGENTS_MD_BYTES} B",
        "passed": agents_ok,
    }
    metrics.append(m_agents)
    if not agents_ok:
        failed_items.append(m_agents)

    # 4b. 主要5フェーズの読込バイト数と削減率
    phase_reductions: List[float] = []
    for phase_key, file_list in PHASE_READ_SETS.items():
        actual_sum = sum(file_sizes[p] for p in file_list)
        base_val = baseline[phase_key]
        red_pct = round((base_val - actual_sum) / max(1, base_val) * 100.0, 2)
        phase_reductions.append(red_pct)
        ok = red_pct >= MIN_REDUCTION_PCT
        item = {
            "key": phase_key,
            "label": METRIC_LABELS[phase_key],
            "baseline": base_val,
            "actual": actual_sum,
            "unit": "B",
            "reduction_pct": red_pct,
            "threshold": f">= {MIN_REDUCTION_PCT:.1f}% 削減",
            "passed": ok,
        }
        metrics.append(item)
        if not ok:
            failed_items.append(item)

    # 4c. 1フェーズのCLI検証回数
    cli_base = baseline["cli_checks_per_phase"]
    cli_red = round((cli_base - cli_count) / max(1, cli_base) * 100.0, 2)
    cli_ok = cli_count <= MAX_CLI_CHECKS_PER_PHASE
    m_cli = {
        "key": "cli_checks_per_phase",
        "label": METRIC_LABELS["cli_checks_per_phase"],
        "baseline": cli_base,
        "actual": cli_count,
        "unit": "回",
        "reduction_pct": cli_red,
        "threshold": f"<= {MAX_CLI_CHECKS_PER_PHASE} 回",
        "passed": cli_ok,
    }
    metrics.append(m_cli)
    if not cli_ok:
        failed_items.append(m_cli)

    overall_passed = len(failed_items) == 0
    status = "PASS" if overall_passed else "FAIL"
    min_red = min(phase_reductions) if phase_reductions else 0.0
    max_red = max(phase_reductions) if phase_reductions else 0.0

    summary_line = (
        f"DADA-BENCHMARK: {status} | agents_md={agents_bytes}B | "
        f"reduction={min_red:.1f}%~{max_red:.1f}% | cli_checks={cli_count}"
    )
    if failed_items:
        fail_desc = ", ".join(f"{it['key']}={it['actual']}{it['unit']}({it['reduction_pct']:.1f}%)" for it in failed_items)
        summary_line += f" | failed=[{fail_desc}]"

    return {
        "status": status,
        "passed": overall_passed,
        "root": root.as_posix(),
        "metrics": metrics,
        "failed_items": failed_items,
        "cli_details": cli_details,
        "summary_line": summary_line,
    }


def render_markdown_report(result: Dict[str, Any]) -> str:
    """
    関数名：render_markdown_report
    戻り値：Markdown形式のベンチマーク比較表文字列
    引数：result (Dict[str, Any]) - measure_workspace の返却辞書
    関数の概要：全7指標のベースライン比較表および未達項目一覧をMarkdown文字列へ整形する。
    対応機能ID（トレーサビリティ）：UNIT-009 (REQ-001, REQ-007)
    """
    lines = [
        "# DADA v7.0 ベースライン比較ベンチマーク結果 (dada_benchmark.py)",
        "",
        f"- 計測対象ルート: `{result['root']}`",
        f"- 総合判定: **{result['status']}**",
        "",
        "| 指標ID | 評価指標 | v6.1.0 基準値 | 現在実測値 | 削減率 | 目標閾値 | 判定 |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for m in result["metrics"]:
        judge = "PASS" if m["passed"] else "FAIL"
        lines.append(
            f"| `{m['key']}` | {m['label']} | {m['baseline']}{m['unit']} | "
            f"{m['actual']}{m['unit']} | {m['reduction_pct']:.1f}% | {m['threshold']} | {judge} |"
        )

    if result["failed_items"]:
        lines.extend(["", "## 未達項目一覧"])
        for f in result["failed_items"]:
            lines.append(
                f"- **{f['key']}** ({f['label']}): 実測値 `{f['actual']}{f['unit']}` "
                f"(削減率 `{f['reduction_pct']:.1f}%`) / 目標 `{f['threshold']}`"
            )

    lines.extend(["", result["summary_line"]])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """
    関数名：build_parser
    戻り値：設定済み ArgumentParser インスタンス
    引数：なし
    関数の概要：SW205 5.2節 表8のACI仕様に準拠したCLI引数パーサを構築する。
    対応機能ID（トレーサビリティ）：UNIT-009 (REQ-007)
    """
    parser = argparse.ArgumentParser(
        description="DADAプロセス v7.0 ベースライン比較ベンチマークツール (dada_benchmark.py)"
    )
    parser.add_argument(
        "--root",
        default=".",
        help="計測対象リポジトリルート（既定: .）",
    )
    parser.add_argument(
        "--baseline",
        default="v6.1.0",
        help="ベースライン名 ('v6.1.0') または JSON ファイルパス（既定: v6.1.0）",
    )
    parser.add_argument(
        "--format",
        dest="out_format",
        default="markdown",
        choices=["markdown", "json"],
        help="出力形式 ('markdown' または 'json' / 既定: markdown)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="DADA-BENCHMARK 1行要約のみを標準出力へ表示する",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """
    関数名：main
    戻り値：終了コード (0=全目標達成, 1=1項目以上未達, 2=計測エラー)
    引数：argv (Optional[List[str]]) - コマンドライン引数（None時はsys.argv[1:]）
    関数の概要：ベースライン読込・ワークスペース計測・対比表出力・終了コード判定を実行する。
    対応機能ID（トレーサビリティ）：UNIT-009 (REQ-001, REQ-007)
    """
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code != 0 else 0

    root = Path(args.root).resolve()
    try:
        baseline = load_baseline(args.baseline)
        result = measure_workspace(root, baseline)
    except BenchmarkMeasurementError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    if args.summary:
        print(result["summary_line"])
    elif args.out_format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown_report(result))

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
