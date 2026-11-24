#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル名：tools/dada_verify.py
バージョン番号：1.0.0
作成日：2026-11-24
プログラマ名：DADA Programmer Agent
ファイルの概要：
    DADAプロセス v7.0 の統合機械検証CLI（UNIT-008）。
    単一プロセス内で既存の4つの検証モジュール（dada_check, asdoq_lint, style_check,
    agent_def_check）の検査関数を直接呼び出し、重複する曖昧語・指示語・長文指摘を
    (line, normalized_category) で直交正規化して重複排除する。
    さらに docs/process/.verify_cache.json を用いた SHA-256 検証キャッシュ再利用と、
    docs/process/check_report.md への統合レポート出力を行う。
対応機能ID（トレーサビリティ）：
    UNIT-008 (REQ-003, REQ-004, REQ-008)
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 同一ディレクトリ（tools/）からのモジュール直接インポートを可能にする
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import agent_def_check  # noqa: E402
import asdoq_lint  # noqa: E402
import dada_check  # noqa: E402
import style_check  # noqa: E402


# ---------------------------------------------------------------------------
# 定数定義（データ定義コメント付き）
# ---------------------------------------------------------------------------

# 重要度ラベル定数（既存4CLIと同一基準）
HIGH = "High"
MID = "Mid"
CHECK = "要確認"

# 重要度の優先順位マップ（重複排除時に上位重要度を優先保持する）
SEVERITY_RANK: Dict[str, int] = {HIGH: 0, MID: 1, CHECK: 2}

# 有効な --phase 引数一覧（SW205 5.1節 表7準拠）
VALID_PHASES: Tuple[str, ...] = ("1", "2", "3", "4", "all")

# 有効な --profile 引数一覧（SW205 5.1節 表7準拠）
VALID_PROFILES: Tuple[str, ...] = ("sw105", "swp6", "sw205", "general")

# 有効な --decision1 引数一覧（既定 off）
VALID_DECISION1_MODES: Tuple[str, ...] = ("off", "on")

# 統合レポートおよびキャッシュファイルの相対パス（ルート固定パス）
CHECK_REPORT_REL = Path("docs/process/check_report.md")
VERIFY_CACHE_REL = Path("docs/process/.verify_cache.json")

# 1カテゴリあたりの最大表示件数（トークン節約上限）
MAX_RENDER_ITEMS = 50

# 直交正規化用のルールIDマッピング（asdoq_lint と dada_check / style_check の重複排除用）
ASDOQ_AMBIGUOUS_RULE_IDS = {
    "RULE-101", "RULE-102", "RULE-103", "RULE-104", "RULE-105", "RULE-106", "RULE-107",
}
ASDOQ_DEIXIS_RULE_IDS = {"RULE-108"}
ASDOQ_LONG_SENTENCE_RULE_IDS = {"RULE-610"}
ASDOQ_AI_METAPHOR_RULE_IDS = {"RULE-303", "RULE-304", "RULE-305", "RULE-307", "RULE-308"}
ASDOQ_AI_JARGON_RULE_IDS = {"RULE-309", "RULE-310"}
ASDOQ_CONTRAST_RULE_IDS = {"RULE-306"}
ASDOQ_DASH_RULE_IDS = {"RULE-505"}
ASDOQ_VERBOSE_RULE_IDS = {"RULE-404", "RULE-405", "RULE-406", "RULE-408", "RULE-409"}
ASDOQ_TBD_RULE_IDS = {"RULE-702"}
ASDOQ_SKELETON_RULE_IDS = {"RULE-803"}


# ---------------------------------------------------------------------------
# 汎用ヘルパ関数
# ---------------------------------------------------------------------------

def _rel_path(root: Path, path: Path) -> str:
    """
    関数名：_rel_path
    戻り値：ルート基準のPOSIX形式相対パス（ルート外の場合はPOSIX絶対パス）
    引数：root (Path) - リポジトリルート, path (Path) - 対象ファイルパス
    関数の概要：パス表記をOS非依存のPOSIX形式へ正規化する。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-004)
    """
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _sha256_file(path: Path) -> str:
    """
    関数名：_sha256_file
    戻り値：ファイルのSHA-256 16進ダイジェスト文字列
    引数：path (Path) - 対象ファイルパス
    関数の概要：キャッシュ一致判定のため対象ファイルのSHA-256ハッシュを計算する。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-004, REQ-008)
    """
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_location(loc_str: str) -> Tuple[str, int]:
    """
    関数名：_parse_location
    戻り値：(ファイルパス部, 先頭行番号) のタプル（行番号なし時は0）
    引数：loc_str (str) - 既存ツールが出力したlocation文字列
    関数の概要：`path:line` や `path:line / ID` 形式の位置表記をファイルと行番号に分解する。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-004)
    """
    head = loc_str.split(" / ", 1)[0].strip()
    m = re.match(r"^(.*?):(\d+)(?:,\d+)*$", head)
    if m:
        return m.group(1).strip(), int(m.group(2))
    return head, 0


def normalize_category(finding: Dict[str, Any]) -> str:
    """
    関数名：normalize_category
    戻り値：直交正規化後のカテゴリ識別子文字列
    引数：finding (Dict[str, Any]) - 正規化対象の指摘辞書
    関数の概要：
        既存ツール間で重複する曖昧語・指示語・長文・AI-Slop・TBD・スケルトン残骸の
        指摘カテゴリを共通キーへ正規化し、重複排除を可能にする。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-004)
    """
    source = finding.get("source", "")
    rule_id = finding.get("rule_id", "")
    category = finding.get("category", "")
    message = finding.get("message", "")

    # 1. 曖昧語の正規化
    if source == "dada_check" and "曖昧語" in message:
        return "ambiguous_word"
    if source == "asdoq_lint" and rule_id in ASDOQ_AMBIGUOUS_RULE_IDS:
        return "ambiguous_word"

    # 2. 指示語の正規化
    if source == "dada_check" and "指示語" in message:
        return "deixis"
    if source == "asdoq_lint" and rule_id in ASDOQ_DEIXIS_RULE_IDS:
        return "deixis"

    # 3. 長文指摘の正規化
    if source == "style_check" and "長文" in category:
        return "long_sentence"
    if source == "asdoq_lint" and rule_id in ASDOQ_LONG_SENTENCE_RULE_IDS:
        return "long_sentence"

    # 4. AI-Slop / 冗長表現 / ダッシュ記号の正規化
    if source == "style_check" and "AI比喩" in category:
        return "ai_metaphor_slop"
    if source == "asdoq_lint" and rule_id in ASDOQ_AI_METAPHOR_RULE_IDS:
        return "ai_metaphor_slop"

    if source == "style_check" and "AI頻出語彙" in category:
        return "ai_jargon_slop"
    if source == "asdoq_lint" and rule_id in ASDOQ_AI_JARGON_RULE_IDS:
        return "ai_jargon_slop"

    if source == "style_check" and "過剰な否定対比" in category:
        return "contrast_slop"
    if source == "asdoq_lint" and rule_id in ASDOQ_CONTRAST_RULE_IDS:
        return "contrast_slop"

    if source == "style_check" and "ダッシュ記号" in category:
        return "dash_slop"
    if source == "asdoq_lint" and rule_id in ASDOQ_DASH_RULE_IDS:
        return "dash_slop"

    if source == "style_check" and "冗長表現" in category:
        return "verbose_slop"
    if source == "asdoq_lint" and rule_id in ASDOQ_VERBOSE_RULE_IDS:
        return "verbose_slop"

    # 5. TBD・スケルトン残骸の正規化
    if source == "dada_check" and "TBD" in message:
        return "tbd_unresolved"
    if source == "asdoq_lint" and rule_id in ASDOQ_TBD_RULE_IDS:
        return "tbd_unresolved"

    if source == "dada_check" and "スケルトン" in message:
        return "skeleton_leftover"
    if source == "asdoq_lint" and rule_id in ASDOQ_SKELETON_RULE_IDS:
        return "skeleton_leftover"

    # 非重複カテゴリの個別キー生成
    tag = rule_id or category or "general"
    return f"{source}:{tag}:{message[:40]}"


def deduplicate_findings(findings: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    関数名：deduplicate_findings
    戻り値：(重複排除後の指摘リスト, 排除された重複件数)
    引数：findings (List[Dict[str, Any]]) - 統合前の全指摘リスト
    関数の概要：
        (file, line, normalized_category) を直交キーとして重複指摘を統合する。
        同一ファイル対象時は (line, normalized_category) で重複を1件へ集約し、
        より高い重要度と詳細な改善ヒントを保持する。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-004)
    """
    dedup_map: Dict[Tuple[str, int, str], Dict[str, Any]] = {}
    ordered_keys: List[Tuple[str, int, str]] = []
    removed_count = 0

    for item in findings:
        norm_cat = normalize_category(item)
        item_file = item.get("file", "")
        item_line = int(item.get("line", 0))
        key = (item_file, item_line, norm_cat)

        if key not in dedup_map:
            enriched = dict(item)
            enriched["normalized_category"] = norm_cat
            enriched["sources"] = [item["source"]]
            dedup_map[key] = enriched
            ordered_keys.append(key)
        else:
            removed_count += 1
            existing = dedup_map[key]
            if item["source"] not in existing["sources"]:
                existing["sources"].append(item["source"])
            # 上位の重要度を優先保持する
            new_rank = SEVERITY_RANK.get(item["severity"], 9)
            old_rank = SEVERITY_RANK.get(existing["severity"], 9)
            if new_rank < old_rank:
                existing["severity"] = item["severity"]
            if len(item.get("hint", "")) > len(existing.get("hint", "")):
                existing["hint"] = item["hint"]

    result = [dedup_map[k] for k in ordered_keys]
    result.sort(key=lambda x: (SEVERITY_RANK.get(x["severity"], 9), x.get("file", ""), int(x.get("line", 0))))
    return result, removed_count


# ---------------------------------------------------------------------------
# スナップショット・ターゲット解決・キャッシュ管理
# ---------------------------------------------------------------------------

def _find_style_snapshot(root: Path, target_file: Path, raw_input: Optional[str]) -> Optional[Tuple[Path, Path]]:
    """
    関数名：_find_style_snapshot
    戻り値：(snapshotファイルパス, style_checkへ渡すパス表記) または None
    引数：root (Path) - リポジトリルート, target_file (Path) - 検査対象ファイル, raw_input (Optional[str]) - --input指定文字列
    関数の概要：root/docs/process/.style_snapshots 配下に存在する対象ファイルの意味スナップショットを探索する。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-003, REQ-004)
    """
    snap_dir = root / "docs" / "process" / ".style_snapshots"
    if not snap_dir.is_dir():
        return None

    candidates: List[Path] = []
    if raw_input:
        candidates.append(Path(raw_input))
    try:
        candidates.append(target_file.resolve().relative_to(root.resolve()))
    except ValueError:
        pass
    candidates.append(target_file)
    candidates.append(target_file.resolve())

    for cand in candidates:
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", cand.as_posix())
        snap_path = snap_dir / f"{safe_name}.json"
        if snap_path.is_file():
            return snap_path, cand
    return None


def _collect_scope_files(root: Path, phase: str, input_path: Optional[Path]) -> List[Path]:
    """
    関数名：_collect_scope_files
    戻り値：ハッシュ計算対象となるファイルパスのソート済みリスト
    引数：root (Path) - リポジトリルート, phase (str) - 対象フェーズ, input_path (Optional[Path]) - 指定入力ファイル
    関数の概要：SHA-256 キャッシュ判定に用いる全入力ファイルを漏れなく収集する。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-004, REQ-008)
    """
    tracked: set[Path] = set()

    if input_path is not None and input_path.is_file():
        tracked.add(input_path.resolve())
        snap_dir = root / "docs" / "process" / ".style_snapshots"
        if snap_dir.is_dir():
            for sp in snap_dir.glob("*.json"):
                tracked.add(sp.resolve())

    art_dir = root / "docs" / "artifacts"
    if art_dir.is_dir():
        for p in art_dir.glob("*.md"):
            if p.name.startswith(("SW105", "SWP6", "SW205", "REV101", "BUG101")):
                tracked.add(p.resolve())

    if phase in ("3", "4", "all"):
        agents_dir = root / ".agents"
        if agents_dir.is_dir():
            for p in agents_dir.rglob("*.md"):
                tracked.add(p.resolve())
        guide_dir = root / "docs" / "guidelines"
        if guide_dir.is_dir():
            for p in guide_dir.glob("*.md"):
                tracked.add(p.resolve())
        eval_rep = root / "docs" / "process" / "eval_report.md"
        if eval_rep.is_file():
            tracked.add(eval_rep.resolve())

    if phase in ("4", "all"):
        for sub in ("tools", "tests"):
            sub_dir = root / sub
            if sub_dir.is_dir():
                for p in sub_dir.glob("*.py"):
                    tracked.add(p.resolve())

    return sorted(tracked)


def _compute_file_hashes(root: Path, files: List[Path]) -> Dict[str, str]:
    """
    関数名：_compute_file_hashes
    戻り値：{相対パス: SHA-256} の辞書
    引数：root (Path) - リポジトリルート, files (List[Path]) - ハッシュ対象ファイル一覧
    関数の概要：各ファイルのSHA-256ダイジェストを計算して辞書化する。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-004, REQ-008)
    """
    hashes: Dict[str, str] = {}
    for fpath in files:
        if fpath.is_file():
            hashes[_rel_path(root, fpath)] = _sha256_file(fpath)
    return hashes


def _build_cache_key(phase: str, input_path: Optional[Path], root: Path, profile: str, decision1: str) -> str:
    """
    関数名：_build_cache_key
    戻り値：正規化されたJSON文字列のキャッシュキー
    引数：phase, input_path, root, profile, decision1
    関数の概要：CLI引数一式から一意なキャッシュキー文字列を構築する。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-004, REQ-008)
    """
    input_key = _rel_path(root, input_path) if input_path is not None else ""
    return json.dumps(
        {
            "phase": phase,
            "input": input_key,
            "profile": profile,
            "decision1": decision1,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


# ---------------------------------------------------------------------------
# 統合検証実行エンジン
# ---------------------------------------------------------------------------

def _resolve_asdoq_targets(
    root: Path,
    phase: str,
    input_path: Optional[Path],
    profile: str,
    docs: Dict[str, Any],
) -> List[Tuple[Path, str]]:
    """
    関数名：_resolve_asdoq_targets
    戻り値：(検査対象ファイルPath, プロファイル名) のリスト
    引数：root, phase, input_path, profile, docs
    関数の概要：--input または --phase に応じて ASDoQ / Style 検査の対象ファイル群を決定する。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-003, REQ-004)
    """
    if input_path is not None:
        return [(input_path, profile)]

    targets: List[Tuple[Path, str]] = []
    phase_doc_map = {
        "1": [("SW105", "sw105")],
        "2": [("SWP6", "swp6")],
        "3": [("SW205", "sw205")],
        "4": [],
        "all": [("SW105", "sw105"), ("SWP6", "swp6"), ("SW205", "sw205")],
    }
    for doc_id, default_prof in phase_doc_map.get(phase, []):
        if doc_id in docs:
            chosen_prof = profile if profile != "general" else default_prof
            targets.append((docs[doc_id].path, chosen_prof))
    return targets


def run_verification(
    root: Path,
    phase: str = "all",
    input_path: Optional[Path] = None,
    raw_input: Optional[str] = None,
    profile: str = "general",
    decision1: str = "off",
    reuse_cache: bool = False,
    no_report: bool = False,
) -> Dict[str, Any]:
    """
    関数名：run_verification
    戻り値：検証結果辞書（findings, counts, verdict, cache_status, report_markdown, summary_line, exit_code）
    引数：
        root (Path) - リポジトリルート
        phase (str) - 対象フェーズ ('1'|'2'|'3'|'4'|'all')
        input_path (Optional[Path]) - 個別検査対象 .md パス
        raw_input (Optional[str]) - CLIで渡された元の --input 文字列
        profile (str) - ASDoQプロファイル ('sw105'|'swp6'|'sw205'|'general')
        decision1 (str) - gemini-decision-1 モード ('off'|'on')
        reuse_cache (bool) - SHA-256 キャッシュ再利用有無
        no_report (bool) - check_report.md 出力抑止フラグ
    関数の概要：
        既存4検査エンジンを単一プロセスで直交実行し、重複排除・キャッシュ管理・
        統合レポート生成・終了コード判定を一貫して行う。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-003, REQ-004, REQ-008)
    """
    start_ts = time.perf_counter()

    # 1. キャッシュキーおよび対象ファイル群のSHA-256ハッシュを計算する
    scope_files = _collect_scope_files(root, phase, input_path)
    file_hashes = _compute_file_hashes(root, scope_files)
    cache_key = _build_cache_key(phase, input_path, root, profile, decision1)
    cache_file = root / VERIFY_CACHE_REL
    scope_label = f"phase={phase}" + (f",input={_rel_path(root, input_path)}" if input_path else "")

    cache_data: Dict[str, Any] = {"entries": {}}
    if cache_file.is_file():
        try:
            loaded = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("entries"), dict):
                cache_data = loaded
        except Exception:
            cache_data = {"entries": {}}

    # 2. --reuse-cache 指定時にSHA-256ハッシュと引数キーを照合し、一致時は解析を省略する
    if reuse_cache:
        entry = cache_data["entries"].get(cache_key)
        if isinstance(entry, dict) and entry.get("file_hashes") == file_hashes:
            elapsed = round(time.perf_counter() - start_ts, 4)
            high_c = int(entry.get("high", 0))
            mid_c = int(entry.get("mid", 0))
            chk_c = int(entry.get("check", 0))
            verdict = "NG" if high_c > 0 else ("WARN" if mid_c > 0 else "OK")
            summary_line = (
                f"DADA-VERIFY: {verdict} | scope={scope_label} | "
                f"High={high_c} / Mid={mid_c} / 要確認={chk_c} | "
                f"cache=HIT | decision1={decision1} | elapsed={elapsed}s"
            )
            report_md = str(entry.get("report_markdown", ""))
            if not report_md:
                report_md = f"# DADA 統合機械検証レポート\n\n- {summary_line}\n"
            elif "DADA-VERIFY:" in report_md:
                report_md = re.sub(r"DADA-VERIFY:[^\n]*", summary_line, report_md)

            if not no_report:
                out_report = root / CHECK_REPORT_REL
                out_report.parent.mkdir(parents=True, exist_ok=True)
                out_report.write_text(report_md, encoding="utf-8")

            return {
                "exit_code": 1 if high_c > 0 else 0,
                "verdict": verdict,
                "cache_status": "HIT",
                "counts": {HIGH: high_c, MID: mid_c, CHECK: chk_c},
                "summary_line": summary_line,
                "report_markdown": report_md,
                "findings": entry.get("findings", []),
                "deduplicated_count": int(entry.get("deduplicated_count", 0)),
            }

    cache_status = "MISS" if reuse_cache else "OFF"
    raw_findings: List[Dict[str, Any]] = []
    notes: List[str] = []

    # 3. dada_check の各検査を実行する
    docs = dada_check.load_docs(root)
    dada_sections: List[dada_check.Section] = [
        dada_check.check_trace(root, docs),
        dada_check.check_lint(root, docs),
    ]
    if phase in ("4", "all"):
        dada_sections.append(dada_check.check_code(root, docs))
    dada_sections.append(dada_check.check_status(root))

    for sec in dada_sections:
        for n in sec.notes:
            notes.append(f"[dada_check] {n}")
        for f in sec.findings:
            f_path, f_line = _parse_location(f.location)
            raw_findings.append({
                "source": "dada_check",
                "section": sec.title,
                "severity": f.severity,
                "file": f_path,
                "line": f_line,
                "rule_id": "",
                "category": sec.title,
                "message": f.message,
                "hint": f.hint,
            })

    # 4. asdoq_lint と style_check を対象文書に対して単一パスで実行する
    asdoq_targets = _resolve_asdoq_targets(root, phase, input_path, profile, docs)
    if asdoq_targets:
        local_dict = root / "tools" / "asdoq_dictionary.json"
        dict_path = local_dict if local_dict.is_file() else (TOOLS_DIR / "asdoq_dictionary.json")
        ruleset = asdoq_lint.load_dictionary(dict_path)
        l1_client = None
        if decision1 == "on":
            api_key, _key_source = asdoq_lint.resolve_gemini_api_key(base_dir=root)
            if api_key:
                l1_client = asdoq_lint.RestDecision1Client(api_key=api_key)

        for target_file, target_prof in asdoq_targets:
            rel_target = _rel_path(root, target_file)
            raw_doc = target_file.read_text(encoding="utf-8-sig", errors="replace")

            # 4a. Layer 0 検査と Layer 1 選別
            layer0 = asdoq_lint.analyze_document_layer0(
                text=raw_doc,
                ruleset=ruleset,
                profile=target_prof,
                characteristic="all",
                max_items=25,
            )
            layer1 = asdoq_lint.evaluate_layer1_decision1(
                candidate_slices=layer0["candidate_slices"],
                decision1_mode=decision1,
                threshold=0.30,
                client=l1_client,
                document_excerpt=raw_doc[:120000],
            )
            notes.append(
                f"[asdoq_lint] {rel_target} (profile={target_prof}, "
                f"decision1={layer1['decision1_mode']}, slices={len(layer0['candidate_slices'])})"
            )
            for f in layer0["confirmed_findings"]:
                raw_findings.append({
                    "source": "asdoq_lint",
                    "section": "ASDoQ 違反例辞書・構造検査",
                    "severity": f["severity"],
                    "file": rel_target,
                    "line": int(f.get("line", 0)),
                    "rule_id": f.get("rule_id", ""),
                    "category": f.get("asdoq_label", ""),
                    "message": f"該当=`{f.get('matched', '')}`",
                    "hint": f.get("hint", ""),
                })

            # 4b. style_check (AI-Slop + スナップショット意味保持検証)
            style_findings, _style_sum = style_check.lint_markdown_style(target_file)
            for f in style_findings:
                raw_findings.append({
                    "source": "style_check",
                    "section": "日本語推敲・AI-Slop検査",
                    "severity": f["severity"],
                    "file": rel_target,
                    "line": int(f.get("line", 0)),
                    "rule_id": "",
                    "category": f.get("category", ""),
                    "message": f"{f.get('message', '')}（該当: `{f.get('matched', '')}`）",
                    "hint": f.get("hint", ""),
                })

            snap_info = _find_style_snapshot(root, target_file, raw_input)
            if snap_info is not None:
                _snap_path, snap_target_arg = snap_info
                orig_snap_dir = style_check.SNAPSHOT_DIR
                try:
                    style_check.SNAPSHOT_DIR = root / "docs" / "process" / ".style_snapshots"
                    high_issues, chk_issues, _v_sum = style_check.verify_against_snapshot(snap_target_arg)
                finally:
                    style_check.SNAPSHOT_DIR = orig_snap_dir
                for hi in high_issues:
                    raw_findings.append({
                        "source": "style_check",
                        "section": "推敲意味保持検証 (verify)",
                        "severity": HIGH,
                        "file": rel_target,
                        "line": 0,
                        "rule_id": "STYLE-VERIFY-HIGH",
                        "category": "意味保持違反",
                        "message": hi,
                        "hint": "推敲前のID・数値・見出し・表構造を復元する",
                    })
                for ci in chk_issues:
                    raw_findings.append({
                        "source": "style_check",
                        "section": "推敲意味保持検証 (verify)",
                        "severity": CHECK,
                        "file": rel_target,
                        "line": 0,
                        "rule_id": "STYLE-VERIFY-CHECK",
                        "category": "意味極性変化疑義",
                        "message": ci,
                        "hint": "否定・義務表現の意図を確認する",
                    })

    # 5. agent_def_check の実行（Phase 3 / 4 / all かつ .agents 存在時）
    if phase in ("3", "4", "all") and (root / ".agents").is_dir():
        def_files = agent_def_check.iter_definition_files(root, list(agent_def_check.DEFAULT_SCAN_DIRS))
        adc_sections = [
            agent_def_check.check_skill(root, def_files),
            agent_def_check.check_command(root, def_files),
            agent_def_check.check_pokayoke(root, def_files),
        ]
        if phase in ("4", "all"):
            adc_sections.append(agent_def_check.check_unit(root))
            adc_sections.append(agent_def_check.check_eval(root))

        for sec in adc_sections:
            for n in sec.notes:
                notes.append(f"[agent_def_check] {n}")
            for f in sec.findings:
                f_path, f_line = _parse_location(f.location)
                raw_findings.append({
                    "source": "agent_def_check",
                    "section": sec.title,
                    "severity": f.severity,
                    "file": f_path,
                    "line": f_line,
                    "rule_id": "",
                    "category": sec.title,
                    "message": f.message,
                    "hint": f.hint,
                })

    # 6. 直交正規化による重複排除と集計
    deduped, removed_count = deduplicate_findings(raw_findings)
    counts = {
        HIGH: sum(1 for x in deduped if x["severity"] == HIGH),
        MID: sum(1 for x in deduped if x["severity"] == MID),
        CHECK: sum(1 for x in deduped if x["severity"] == CHECK),
    }
    verdict = "NG" if counts[HIGH] > 0 else ("WARN" if counts[MID] > 0 else "OK")
    elapsed = round(time.perf_counter() - start_ts, 4)

    summary_line = (
        f"DADA-VERIFY: {verdict} | scope={scope_label} | "
        f"High={counts[HIGH]} / Mid={counts[MID]} / 要確認={counts[CHECK]} | "
        f"cache={cache_status} | decision1={decision1} | elapsed={elapsed}s"
    )

    report_md = render_verify_report(
        summary_line=summary_line,
        verdict=verdict,
        counts=counts,
        findings=deduped,
        notes=notes,
        removed_count=removed_count,
        phase=phase,
        profile=profile,
        decision1=decision1,
        cache_status=cache_status,
    )

    # 7. レポート出力およびキャッシュ保存（--no-report 時はファイル出力を抑止）
    if not no_report:
        out_report = root / CHECK_REPORT_REL
        out_report.parent.mkdir(parents=True, exist_ok=True)
        out_report.write_text(report_md, encoding="utf-8")

        cache_data["entries"][cache_key] = {
            "file_hashes": file_hashes,
            "high": counts[HIGH],
            "mid": counts[MID],
            "check": counts[CHECK],
            "verdict": verdict,
            "scope": scope_label,
            "deduplicated_count": removed_count,
            "findings": deduped[:MAX_RENDER_ITEMS],
            "report_markdown": report_md,
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "exit_code": 1 if counts[HIGH] > 0 else 0,
        "verdict": verdict,
        "cache_status": cache_status,
        "counts": counts,
        "summary_line": summary_line,
        "report_markdown": report_md,
        "findings": deduped,
        "deduplicated_count": removed_count,
    }


def render_verify_report(
    summary_line: str,
    verdict: str,
    counts: Dict[str, int],
    findings: List[Dict[str, Any]],
    notes: List[str],
    removed_count: int,
    phase: str,
    profile: str,
    decision1: str,
    cache_status: str,
) -> str:
    """
    関数名：render_verify_report
    戻り値：Markdown形式の統合検証レポート文字列
    引数：summary_line, verdict, counts, findings, notes, removed_count, phase, profile, decision1, cache_status
    関数の概要：統合機械検証の全指摘と直交重複排除結果を人間・AIが読みやすいMarkdownに整形する。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-004)
    """
    lines = [
        "# DADA 統合機械検証レポート (dada_verify.py)",
        "",
        f"- 実行日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 対象フェーズ: `{phase}` / プロファイル: `{profile}` / `--decision1`: `{decision1}` / キャッシュ: `{cache_status}`",
        f"- 判定: **{verdict}**（High {counts[HIGH]} / Mid {counts[MID]} / 要確認 {counts[CHECK]} / 重複統合 {removed_count} 件）",
        "",
        "## 1. 検査サマリ情報",
    ]
    if notes:
        for n in notes:
            lines.append(f"- {n}")
    else:
        lines.append("- 特記事項なし")

    lines.extend(["", "## 2. 検出された指摘一覧（直交重複排除済み）"])
    if not findings:
        lines.append("- 指摘なし")
    else:
        for f in findings[:MAX_RENDER_ITEMS]:
            loc = f"{f['file']}:{f['line']}" if f.get("line", 0) > 0 else (f.get("file") or "-")
            srcs = ",".join(f.get("sources", [f.get("source", "")]))
            hint_part = f"（対応: {f['hint']}）" if f.get("hint") else ""
            lines.append(
                f"- [{f['severity']}] {loc} ({f['normalized_category']} / {srcs}): "
                f"{f['message']}{hint_part}"
            )
        if len(findings) > MAX_RENDER_ITEMS:
            lines.append(f"- ...他 {len(findings) - MAX_RENDER_ITEMS} 件省略（上位 {MAX_RENDER_ITEMS} 件を表示）")

    lines.extend(["", summary_line, ""])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """
    関数名：build_parser
    戻り値：設定済み ArgumentParser インスタンス
    引数：なし
    関数の概要：SW205 5.1節 表7のACI仕様に準拠したCLI引数パーサを構築する。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-004)
    """
    parser = argparse.ArgumentParser(
        description="DADAプロセス v7.0 統合機械検証CLI (dada_verify.py)"
    )
    parser.add_argument(
        "--phase",
        default="all",
        choices=list(VALID_PHASES),
        help="検証対象フェーズ (1, 2, 3, 4, all / 既定: all)",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="検査対象の個別Markdownファイルパス (.md / 任意)",
    )
    parser.add_argument(
        "--profile",
        default="general",
        choices=list(VALID_PROFILES),
        help="ASDoQ文書種別プロファイル (sw105, swp6, sw205, general / 既定: general)",
    )
    parser.add_argument(
        "--decision1",
        default="off",
        choices=list(VALID_DECISION1_MODES),
        help="Google gemini-decision-1 連携モード (off, on / 既定: off)",
    )
    parser.add_argument(
        "--reuse-cache",
        action="store_true",
        help="docs/process/.verify_cache.json のSHA-256キャッシュを再利用する",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="DADA-VERIFY 1行要約のみを標準出力へ表示する",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="docs/process/check_report.md への出力を抑止する",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="リポジトリルートパス（既定: 本ツールの親の親）",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """
    関数名：main
    戻り値：終了コード (0=Highなし, 1=Highあり, 2=実行エラー)
    引数：argv (Optional[List[str]]) - コマンドライン引数（None時はsys.argv[1:]）
    関数の概要：引数の事前検証、APIキー確認、統合検証実行、および出力と終了コード返却を行う。
    対応機能ID（トレーサビリティ）：UNIT-008 (REQ-003, REQ-004, REQ-008)
    """
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code != 0 else 0

    # 1. ルートディレクトリの検証
    root = Path(args.root).resolve() if args.root else TOOLS_DIR.parent.resolve()
    if not root.is_dir():
        print(f"[ERROR] 指定されたルートディレクトリが存在しません: {root}", file=sys.stderr)
        return 2

    # 2. --input ファイルの存在検証
    resolved_input: Optional[Path] = None
    if args.input is not None:
        cand = Path(args.input)
        if not cand.is_absolute() and not cand.is_file() and (root / cand).is_file():
            cand = root / cand
        if not cand.is_file():
            print(f"[ERROR] 指定された入力ファイルが存在しません: {args.input}", file=sys.stderr)
            return 2
        resolved_input = cand.resolve()

    # 3. --decision1 on 時の GEMINI_API_KEY 事前検証（未設定時は外部通信・推測補完なしで終了コード2）
    if args.decision1 == "on":
        api_key, _source = asdoq_lint.resolve_gemini_api_key(base_dir=root)
        if not api_key:
            print(
                "[ERROR] --decision1 on が指定されましたが、GEMINI_API_KEY（環境変数 / .env.local / .env）"
                "が設定されていません。既定の --decision1 off を使用するか APIキーを設定してください。",
                file=sys.stderr,
            )
            return 2

    # 4. 統合検証の実行
    try:
        result = run_verification(
            root=root,
            phase=args.phase,
            input_path=resolved_input,
            raw_input=args.input,
            profile=args.profile,
            decision1=args.decision1,
            reuse_cache=args.reuse_cache,
            no_report=args.no_report,
        )
    except (asdoq_lint.InputDocumentError, asdoq_lint.DictionaryValidationError, ValueError, RuntimeError) as exc:
        print(f"[ERROR] 検証実行エラー: {exc}", file=sys.stderr)
        return 2

    # 5. 出力と終了コード返却
    if args.summary:
        print(result["summary_line"])
    else:
        print(result["report_markdown"])
    return int(result["exit_code"])


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
