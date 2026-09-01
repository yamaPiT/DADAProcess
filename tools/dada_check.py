#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DADA Process 機械チェッカ (dada_check.py)

目的:
    AIエージェントが「推論」で行うと取りこぼしやすい機械的な検証を、
    決定論的なスクリプトに委譲する。これにより
      (1) 検証の抜け・幻覚（実在しないIDの照合完了報告）を防ぐ
      (2) 全文をコンテキストに読み込まずに済むためトークンを節約する
    の2つを同時に達成する。

前提:
    Python 3.8 以降の標準ライブラリのみ。外部依存なし。

使い方:
    python tools/dada_check.py all        # 全チェック（推奨）
    python tools/dada_check.py trace      # ID対応（REQ↔TC↔UNIT）のみ
    python tools/dada_check.py lint       # 文書の書き方（曖昧語・空欄等）のみ
    python tools/dada_check.py code       # ソースコードとの照合のみ
    python tools/dada_check.py status     # REV101/BUG101 の未解決件数のみ

    オプション:
      --root <path>   リポジトリルート（既定: 本スクリプトの親ディレクトリの親）
      --summary       サマリ1行のみ出力する
      --no-report     docs/process/check_report.md を書き出さない

終了コード:
    0 = High指摘なし / 1 = High指摘あり / 2 = 実行エラー
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

HIGH = "High"
MID = "Mid"
CHECK = "要確認"
SEVERITY_ORDER = {HIGH: 0, MID: 1, CHECK: 2}

MAX_ITEMS_PER_CATEGORY = 25  # 出力の肥大（トークン浪費）を防ぐ上限

# ASDoQ執筆ルール12箇条 第3条の曖昧語（`asdoq_writing_rules.md` と同一に保つこと）
AMBIGUOUS_WORDS = [
    "適切に", "高速に", "柔軟に", "使いやすい", "基本的に",
    "十分な", "可能な限り", "必要に応じて", "正しく", "問題なく", "など",
]
# 「等」は「等しい」「均等」等の正当な用法と区別するため文脈付きで検出する
AMBIGUOUS_PATTERNS = [(re.compile(re.escape(w)), w) for w in AMBIGUOUS_WORDS]
AMBIGUOUS_PATTERNS.append(
    (re.compile(r"(?<![均平対同高不上劣])等(?=[のをはがにでとや、。）\)\s]|$)"), "等")
)

# ASDoQ執筆ルール12箇条 第4条の指示語
DEIXIS_PATTERNS = [
    (re.compile(r"それ(?!ぞれ)"), "それ"),
    (re.compile(r"これ"), "これ"),
    (re.compile(r"上記"), "上記"),
    (re.compile(r"当該"), "当該"),
    (re.compile(r"同様"), "同様"),
]

# TBDの解消計画（時期・方法）が併記されていると判断できる語
TBD_PLAN_HINTS = ("Phase", "phase", "決定", "確定", "確認", "期限", "まで", "時点", "レビュー")
# 「TBD項目」（表の見出し）と「未定義」（別語）を誤検出しないよう境界を付ける
TBD_RE = re.compile(r"TBD(?!項目)|未定(?!義)")

# 文書ID → (ファイル名の先頭一致, スケルトンの相対パス)
DOC_SPECS = {
    "SW105": ("SW105", ".agents/skills/requirements-engineer/references/SW105_skeleton.md"),
    "SWP6": ("SWP6", ".agents/skills/test-engineer/references/SWP6_skeleton.md"),
    "SW205": ("SW205", ".agents/skills/architect/references/SW205_skeleton.md"),
}

# ソースコード走査の対象・除外
SOURCE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".java", ".c", ".h",
    ".cc", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".kt", ".kts",
    ".swift", ".dart", ".vue", ".svelte", ".scala", ".m", ".mm", ".sql",
    ".sh", ".ps1", ".bat",
}
SOURCE_EXCLUDE_DIRS = {
    ".git", ".github", ".agents", "docs", "tools", "scratch", "node_modules",
    ".venv", "venv", "env", "__pycache__", "dist", "build", "out", ".next",
    "target", "coverage", ".pytest_cache", ".mypy_cache", "vendor",
}

# テスト改ざんの疑いがあるマーカー
TAMPER_PATTERNS = [
    (re.compile(r"\.skip\s*\("), "skip されたテスト"),
    (re.compile(r"\.only\s*\("), "only による他テストの除外"),
    (re.compile(r"\b(xit|xdescribe|xtest)\s*\("), "無効化されたテスト"),
    (re.compile(r"pytest\.mark\.skip"), "skip されたテスト"),
    (re.compile(r"@unittest\.skip"), "skip されたテスト"),
    (re.compile(r"@Ignore\b"), "無効化されたテスト"),
    (re.compile(r"\bt\.Skip\s*\("), "skip されたテスト"),
    (re.compile(r"\bit\.todo\s*\("), "未実装のまま残されたテスト"),
]

ID_RE = {
    "REQ": re.compile(r"\bREQ-(\d{1,4}|EX)\b"),
    "TC": re.compile(r"\bTC-(\d{1,4}|EX)\b"),
    "UNIT": re.compile(r"\bUNIT-(\d{1,4}|EX)\b"),
}
HEADING_ID_RE = {
    kind: re.compile(r"^#{2,6}\s*(" + kind + r"-(?:\d{1,4}|EX))\b")
    for kind in ("REQ", "TC", "UNIT")
}
FIELD_RE = re.compile(r"^\s*[-*+]\s*\*\*(.+?)\*\*\s*[:：]\s*(.*)$")
SECTION_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")

# lint の対象とする「規範的な記述」のフィールド名（部分一致）
NORMATIVE_FIELDS = (
    "概要", "入力", "処理", "出力", "異常系", "検証条件", "責務",
    "公開インターフェース", "依存先", "期待", "前提",
)
# SWP6 のテスト表で lint 対象とする列名
NORMATIVE_TC_COLUMNS = ("シナリオ", "前提条件", "入力データ", "期待される出力")


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------

class Finding:
    __slots__ = ("severity", "location", "message", "hint")

    def __init__(self, severity: str, location: str, message: str, hint: str = ""):
        self.severity = severity
        self.location = location
        self.message = message
        self.hint = hint

    def render(self) -> str:
        line = "- [{sev}] {loc}: {msg}".format(
            sev=self.severity, loc=self.location, msg=self.message)
        if self.hint:
            line += "（対応: {}）".format(self.hint)
        return line


class Section:
    """チェック結果の1カテゴリ。"""

    def __init__(self, title: str):
        self.title = title
        self.findings: list[Finding] = []
        self.notes: list[str] = []

    def add(self, severity: str, location: str, message: str, hint: str = "") -> None:
        self.findings.append(Finding(severity, location, message, hint))

    def note(self, text: str) -> None:
        self.notes.append(text)

    def counts(self) -> dict:
        result = {HIGH: 0, MID: 0, CHECK: 0}
        for f in self.findings:
            result[f.severity] = result.get(f.severity, 0) + 1
        return result

    def render(self) -> str:
        lines = ["## {}".format(self.title)]
        for note in self.notes:
            lines.append("- (情報) {}".format(note))
        if not self.findings:
            lines.append("- 指摘なし")
            return "\n".join(lines)
        ordered = sorted(self.findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.location))
        for f in ordered[:MAX_ITEMS_PER_CATEGORY]:
            lines.append(f.render())
        if len(ordered) > MAX_ITEMS_PER_CATEGORY:
            lines.append("- ...他 {} 件（同種の指摘。上記を直すと連鎖的に解消する場合が多い）".format(
                len(ordered) - MAX_ITEMS_PER_CATEGORY))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 汎用ユーティリティ
# ---------------------------------------------------------------------------

def read_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def classify_lines(lines: list[str]) -> list[str]:
    """各行を 'code'（コードブロック内） / 'quote'（引用＝AI向け指示） / 'text' に分類する。"""
    kinds = []
    in_fence = False
    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            kinds.append("code")
            continue
        if in_fence:
            kinds.append("code")
        elif line.lstrip().startswith(">"):
            kinds.append("quote")
        else:
            kinds.append("text")
    return kinds


def split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_separator_row(line: str) -> bool:
    cells = split_row(line)
    if not cells:
        return False
    for c in cells:
        if not c or not re.fullmatch(r":?-{1,}:?", c.replace(" ", "")):
            return False
    return True


def iter_tables(lines: list[str], kinds: list[str]):
    """Markdown表を (header_lineno, header_cells, [(lineno, cells), ...]) で列挙する。"""
    i = 0
    total = len(lines)
    while i < total:
        line = lines[i]
        if kinds[i] == "text" and line.strip().startswith("|"):
            if i + 1 < total and is_separator_row(lines[i + 1]):
                header = split_row(line)
                rows = []
                j = i + 2
                while j < total and lines[j].strip().startswith("|") and kinds[j] == "text":
                    if not is_separator_row(lines[j]):
                        rows.append((j + 1, split_row(lines[j])))
                    j += 1
                yield (i + 1, header, rows)
                i = j
                continue
        i += 1


def collect_ids(text: str, kind: str, include_example: bool = False) -> set:
    found = set()
    for m in ID_RE[kind].finditer(text):
        full = m.group(0)
        if full.endswith("-EX") and not include_example:
            continue
        found.add(full)
    return found


def normalize_id_list(cell: str, kind: str) -> list[str]:
    return sorted(collect_ids(cell, kind))


def find_artifact(root: Path, prefix: str) -> Path | None:
    art_dir = root / "docs" / "artifacts"
    if not art_dir.is_dir():
        return None
    candidates = sorted(p for p in art_dir.glob("*.md") if p.name.startswith(prefix))
    return candidates[0] if candidates else None


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# 文書パーサ
# ---------------------------------------------------------------------------

class Document:
    def __init__(self, doc_id: str, path: Path, root: Path):
        self.doc_id = doc_id
        self.path = path
        self.rel = rel(root, path)
        self.lines = read_lines(path)
        self.kinds = classify_lines(self.lines)
        self.text = "\n".join(self.lines)
        # 引用（AI向け指示）とコードブロックを除いた本文
        self.body_lines = [
            (i + 1, ln) for i, ln in enumerate(self.lines) if self.kinds[i] == "text"
        ]
        self.body_text = "\n".join(ln for _, ln in self.body_lines)

    def headings(self, level: int = 2) -> list[str]:
        result = []
        for i, ln in enumerate(self.lines):
            if self.kinds[i] != "text":
                continue
            m = SECTION_RE.match(ln)
            if m and len(m.group(1)) == level:
                result.append(m.group(2).strip())
        return result

    def id_blocks(self, kind: str) -> list[dict]:
        """`#### REQ-001: 名称` 形式のブロックを抽出する。"""
        blocks = []
        current = None
        for i, ln in enumerate(self.lines):
            if self.kinds[i] == "code":
                if current is not None:
                    current["lines"].append((i + 1, ln))
                continue
            m = HEADING_ID_RE[kind].match(ln)
            if m:
                current = {"id": m.group(1), "lineno": i + 1, "lines": [], "fields": {}}
                blocks.append(current)
                continue
            if SECTION_RE.match(ln) and self.kinds[i] == "text":
                current = None
                continue
            if current is not None:
                current["lines"].append((i + 1, ln))
        for block in blocks:
            last_field = None
            for lineno, ln in block["lines"]:
                fm = FIELD_RE.match(ln)
                if fm:
                    last_field = fm.group(1).strip()
                    block["fields"][last_field] = {"lineno": lineno, "value": fm.group(2).strip()}
                elif last_field and ln.strip().startswith("-"):
                    block["fields"][last_field]["value"] += " " + ln.strip().lstrip("-").strip()
        return blocks

    def field_value(self, block: dict, *names: str) -> str:
        for key, data in block["fields"].items():
            for name in names:
                if name in key:
                    return data["value"]
        return ""

    def tc_table(self) -> tuple[list[str], list[tuple[int, list[str]]]]:
        """SWP6のテスト項目表（テストID列を持つ最大の表）を返す。"""
        best = ([], [])
        for _, header, rows in iter_tables(self.lines, self.kinds):
            if not header:
                continue
            if any("テストID" in h or "テスト ID" in h for h in header):
                data_rows = [(no, cells) for no, cells in rows
                             if cells and ID_RE["TC"].search(cells[0] or "")]
                if len(data_rows) >= len(best[1]):
                    best = (header, data_rows)
        return best

    def column(self, header: list[str], *names: str) -> int:
        for idx, h in enumerate(header):
            for name in names:
                if name in h:
                    return idx
        return -1


# ---------------------------------------------------------------------------
# チェック: トレーサビリティ
# ---------------------------------------------------------------------------

def check_trace(root: Path, docs: dict) -> Section:
    sec = Section("1. トレーサビリティ照合（REQ ↔ TC ↔ UNIT）")

    sw105 = docs.get("SW105")
    swp6 = docs.get("SWP6")
    sw205 = docs.get("SW205")

    if sw105 is None:
        sec.note("SW105 が未作成のため、ID照合をスキップした（Phase 1 開始前であれば正常）。")
        return sec

    req_blocks = sw105.id_blocks("REQ")
    declared_reqs = [b["id"] for b in req_blocks if not b["id"].endswith("-EX")]
    if not declared_reqs:
        fallback = sorted(collect_ids(sw105.body_text, "REQ"))
        if fallback:
            declared_reqs = fallback
            sec.note("SW105 に `#### REQ-001: 名称` 形式の見出しが見つからないため、本文中のREQ-ID出現から一覧を作った。"
                     "スケルトンのブロック形式に揃えることを推奨する。")
        else:
            sec.add(HIGH, sw105.rel, "REQ-IDが1件も定義されていない",
                    "SW105の機能要求を `#### REQ-001: 名称` 形式で定義する")
            return sec
    req_set = set(declared_reqs)
    sec.note("SW105 の REQ-ID: {} 件（{}）".format(len(declared_reqs), summarize_ids(declared_reqs)))

    # --- 要求ブロックの必須フィールド ---
    for block in req_blocks:
        if block["id"].endswith("-EX"):
            continue
        loc = "{}:{} / {}".format(sw105.rel, block["lineno"], block["id"])
        if not sw105.field_value(block, "検証条件", "Acceptance"):
            sec.add(HIGH, loc, "検証条件（Acceptance Criteria）が未記述",
                    "第三者が合否を機械判定できる文（条件＋数値＋期待結果）を書く")
        if not sw105.field_value(block, "異常系"):
            sec.add(MID, loc, "異常系の記述がない",
                    "異常時の挙動を書く。不要な場合は理由を明記する")
        if not sw105.field_value(block, "優先度"):
            sec.add(MID, loc, "優先度（Must/Should/Could）が未設定")

    # --- SWP6 との照合 ---
    if swp6 is None:
        sec.note("SWP6 が未作成のため、REQ↔TC照合をスキップした（Phase 2 開始前であれば正常）。")
    else:
        header, rows = swp6.tc_table()
        if not rows:
            sec.add(HIGH, swp6.rel, "テスト項目表（テストID列を持つ表）が見つからない、または行が0件",
                    "スケルトンの列構成でテスト項目を記述する")
        else:
            col_req = swp6.column(header, "対象要件", "対象要求")
            col_exp = swp6.column(header, "期待")
            col_kind = swp6.column(header, "実行区分")
            covered = {}
            tc_ids = []
            for lineno, cells in rows:
                tc = normalize_id_list(cells[0], "TC")
                tc_id = tc[0] if tc else "TC-?"
                if tc_id.endswith("-EX"):
                    continue
                tc_ids.append(tc_id)
                loc = "{}:{} / {}".format(swp6.rel, lineno, tc_id)
                refs = normalize_id_list(cells[col_req], "REQ") if 0 <= col_req < len(cells) else []
                if not refs:
                    sec.add(HIGH, loc, "対象要件のREQ-IDが未記入",
                            "SW105を開き、対応するREQ-IDを転記する")
                for r in refs:
                    if r.endswith("-EX"):
                        continue
                    if r not in req_set:
                        sec.add(HIGH, loc, "SW105に存在しないREQ-ID `{}` を参照している".format(r),
                                "SW105を開いて正しいIDへ修正する（IDは記憶から書かない）")
                    else:
                        covered.setdefault(r, []).append(tc_id)
                if 0 <= col_kind < len(cells) and not cells[col_kind]:
                    sec.add(HIGH, loc, "実行区分（自動/手動）が未記入",
                            "AIが実行するか人間が実施するかを明示する")
                if 0 <= col_exp < len(cells) and not cells[col_exp]:
                    sec.add(HIGH, loc, "期待される出力が空欄",
                            "SW105の検証条件から数値・具体値を転記する")
                    # 期待値の曖昧語は「2. 文書リント」で検出する（重複出力を避ける）
            dup = [t for t in set(tc_ids) if tc_ids.count(t) > 1]
            if dup:
                sec.add(MID, swp6.rel, "テストIDが重複している: {}".format(", ".join(sorted(dup))))
            missing = [r for r in declared_reqs if r not in covered]
            for r in missing:
                sec.add(HIGH, "{} / {}".format(sw105.rel, r),
                        "対応するTC-IDがSWP6に存在しない",
                        "正常系1件以上＋異常系・境界値1件以上のテスト項目を追加する")
            sec.note("REQ↔TC 対応: {}/{} 件の要求にテスト項目あり".format(
                len(declared_reqs) - len(missing), len(declared_reqs)))

    # --- SW205 との照合 ---
    if sw205 is None:
        sec.note("SW205 が未作成のため、REQ↔UNIT照合をスキップした（Phase 3 開始前であれば正常）。")
    else:
        unit_blocks = [b for b in sw205.id_blocks("UNIT") if not b["id"].endswith("-EX")]
        if not unit_blocks:
            sec.add(HIGH, sw205.rel, "UNIT-IDが1件も定義されていない",
                    "`#### UNIT-001: 名称` 形式で機能ユニットを定義する")
        else:
            unit_ids = {b["id"] for b in unit_blocks}
            covered_by_unit = {}
            deps = {}
            for block in unit_blocks:
                loc = "{}:{} / {}".format(sw205.rel, block["lineno"], block["id"])
                refs = normalize_id_list(sw205.field_value(block, "対応要求", "対応要件"), "REQ")
                if not refs:
                    sec.add(MID, loc, "対応要求（REQ-ID）が未記入。どの要求にも紐づかないユニットは設計の独走",
                            "対応するREQ-IDを転記する。不要なら削除を検討する")
                for r in refs:
                    if r not in req_set:
                        sec.add(HIGH, loc, "SW105に存在しないREQ-ID `{}` を参照している".format(r),
                                "SW105を開いて正しいIDへ修正する")
                    else:
                        covered_by_unit.setdefault(r, []).append(block["id"])
                if not sw205.field_value(block, "公開インターフェース", "公開IF"):
                    sec.add(HIGH, loc, "公開インターフェース（引数・戻り値・エラー）が未定義",
                            "実装が開始できないため必ず定義する")
                if not sw205.field_value(block, "検証条件"):
                    sec.add(MID, loc, "検証条件が未記述",
                            "このユニット単体で合否判定できる条件を書く")
                dep_value = sw205.field_value(block, "依存先")
                dep_ids = [d for d in normalize_id_list(dep_value, "UNIT") if d != block["id"]]
                for d in dep_ids:
                    if d not in unit_ids:
                        sec.add(HIGH, loc, "存在しないUNIT-ID `{}` に依存している".format(d))
                deps[block["id"]] = [d for d in dep_ids if d in unit_ids]

            for cycle in detect_cycles(deps):
                sec.add(HIGH, sw205.rel, "循環依存を検出: {}".format(" → ".join(cycle)),
                        "依存の向きを一方向に整理する（インターフェース抽出や依存性逆転を検討）")

            missing_units = [r for r in declared_reqs if r not in covered_by_unit]
            for r in missing_units:
                sec.add(HIGH, "{} / {}".format(sw105.rel, r),
                        "対応するUNIT-IDがSW205に存在しない",
                        "この要求を実現する機能ユニットを設計する")
            sec.note("REQ↔UNIT 対応: {}/{} 件の要求に設計ユニットあり".format(
                len(declared_reqs) - len(missing_units), len(declared_reqs)))

    return sec


def summarize_ids(ids: list[str]) -> str:
    if len(ids) <= 8:
        return ", ".join(ids)
    return "{} 〜 {} ほか".format(ids[0], ids[-1])


def detect_cycles(deps: dict) -> list[list[str]]:
    """依存グラフから循環を検出する（見つかった経路を返す）。"""
    cycles = []
    seen_signatures = set()
    state = {}

    def visit(node, stack):
        state[node] = 1
        stack.append(node)
        for nxt in deps.get(node, []):
            if state.get(nxt, 0) == 1:
                idx = stack.index(nxt)
                cycle = stack[idx:] + [nxt]
                sig = tuple(sorted(set(cycle)))
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    cycles.append(cycle)
            elif state.get(nxt, 0) == 0:
                visit(nxt, stack)
        stack.pop()
        state[node] = 2

    for node in sorted(deps):
        if state.get(node, 0) == 0:
            visit(node, [])
    return cycles


# ---------------------------------------------------------------------------
# チェック: 文書リント
# ---------------------------------------------------------------------------

def scan_words(text: str, patterns) -> list[str]:
    hits = []
    for pattern, label in patterns:
        if pattern.search(text):
            hits.append(label)
    return hits


def fmt_words(words: list[str]) -> str:
    return "「" + "」「".join(words) + "」"


def normative_spans(doc: Document) -> list[tuple[int, str, str]]:
    """規範的な記述（要求・検証条件・期待値等）を (行番号, ラベル, 本文) で返す。"""
    spans = []
    last_field = None
    for i, ln in enumerate(doc.lines):
        if doc.kinds[i] != "text":
            continue
        m = FIELD_RE.match(ln)
        if m:
            name = m.group(1).strip()
            if any(k in name for k in NORMATIVE_FIELDS):
                last_field = name
                spans.append((i + 1, name, m.group(2).strip()))
            else:
                last_field = None
            continue
        if SECTION_RE.match(ln):
            last_field = None
            continue
        if last_field and ln.strip().startswith("-"):
            spans.append((i + 1, last_field, ln.strip().lstrip("-").strip()))

    for _, header, rows in iter_tables(doc.lines, doc.kinds):
        targets = [(idx, h) for idx, h in enumerate(header)
                   if any(n in h for n in NORMATIVE_TC_COLUMNS)]
        if not targets:
            continue
        for lineno, cells in rows:
            for idx, name in targets:
                if idx < len(cells) and cells[idx]:
                    spans.append((lineno, name, cells[idx]))
    return spans


def skeleton_placeholders(root: Path, doc_id: str) -> set:
    spec = DOC_SPECS.get(doc_id)
    if not spec:
        return set()
    skel = root / spec[1]
    if not skel.is_file():
        return set()
    lines = read_lines(skel)
    kinds = classify_lines(lines)
    found = set()
    for i, line in enumerate(lines):
        # 見出し・AI向け指示（引用）・コードブロックに現れる括弧は、
        # 実文書でも正当な表記なのでプレースホルダとして扱わない
        if kinds[i] != "text" or SECTION_RE.match(line):
            continue
        # 太字の項目名（例: `- **対象（スコープ内）**:`）は実文書でも使う正式なラベルなので除く
        line = re.sub(r"\*\*.*?\*\*", "", line)
        for m in re.finditer(r"（[^（）\n]{1,40}）", line):
            token = m.group(0)
            if any(k in token for k in ("Phase", "推奨", "版数", "例:", "承認ごと")):
                continue
            found.add(token)
    return found


def check_lint(root: Path, docs: dict) -> Section:
    sec = Section("2. 文書リント（ASDoQ執筆ルールの機械検出）")
    if not docs:
        sec.note("対象文書が未作成のためスキップした。")
        return sec

    for doc_id in ("SW105", "SWP6", "SW205"):
        doc = docs.get(doc_id)
        if doc is None:
            continue

        # (a) 規範的記述の曖昧語・指示語
        for lineno, label, text in normative_spans(doc):
            loc = "{}:{}".format(doc.rel, lineno)
            amb = scan_words(text, AMBIGUOUS_PATTERNS)
            if amb:
                sec.add(HIGH, loc, "{}に曖昧語 {} がある".format(label, fmt_words(amb)),
                        "数値・条件・列挙に置き換える（執筆ルール第3条）")
            dei = scan_words(text, DEIXIS_PATTERNS)
            if dei:
                sec.add(HIGH, loc, "{}に指示語 {} があり対象が特定できない".format(label, fmt_words(dei)),
                        "名称・ID・章番号で指す（執筆ルール第4条）")

        # (b) 本文全体は件数のみ（トークン節約と誤検出低減のため）
        outside = 0
        for lineno, ln in doc.body_lines:
            # 表（別途チェック済み）と見出し（標準目次の章名）は対象外
            if ln.strip().startswith("|") or SECTION_RE.match(ln):
                continue
            if scan_words(ln, AMBIGUOUS_PATTERNS) or scan_words(ln, DEIXIS_PATTERNS):
                outside += 1
        if outside:
            sec.note("{}: 規範的記述の外に曖昧語・指示語を含む行が {} 行ある（背景説明での使用は許容。"
                     "要求・仕様に該当する行なら書き直す）".format(doc.rel, outside))

        # (c) TBDの解消計画（見出しと表の列名は対象外）
        for lineno, ln in doc.body_lines:
            if SECTION_RE.match(ln):
                continue
            if TBD_RE.search(ln):
                if not any(h in ln for h in TBD_PLAN_HINTS):
                    sec.add(MID, "{}:{}".format(doc.rel, lineno),
                            "TBD・未定に解消計画（決定時期・決定方法）が併記されていない",
                            "「TBD（Phase 3のADRで決定）」のように時期と方法を書く（執筆ルール第10条）")

        # (d) 表の空欄と列数不一致
        for header_no, header, rows in iter_tables(doc.lines, doc.kinds):
            width = len(header)
            for lineno, cells in rows:
                if all(not c for c in cells):
                    continue
                if len(cells) != width:
                    sec.add(MID, "{}:{}".format(doc.rel, lineno),
                            "表の列数が見出し行（{}行目）と一致しない（{} 列 / 見出し {} 列）".format(
                                header_no, len(cells), width))
                    continue
                empty = [header[i] or "第{}列".format(i + 1)
                         for i, c in enumerate(cells) if not c]
                if empty:
                    sec.add(MID, "{}:{}".format(doc.rel, lineno),
                            "表に空欄がある（列: {}）".format(", ".join(empty)),
                            "該当なしの場合は「なし」「対象外」と書く（執筆ルール第11条）")

        # (e) スケルトンの残骸
        if "【AIへの指示】" in doc.text:
            lines = [str(i + 1) for i, ln in enumerate(doc.lines) if "【AIへの指示】" in ln]
            sec.add(HIGH, "{}:{}".format(doc.rel, ",".join(lines[:5])),
                    "スケルトンの指示コメント【AIへの指示】が残っている", "削除する")
        for kind in ("REQ", "TC", "UNIT"):
            if re.search(r"\b" + kind + r"-EX\b", doc.text):
                sec.add(HIGH, doc.rel, "スケルトンの記入例 `{}-EX` が残っている".format(kind), "削除する")
        if "ADR-EX" in doc.text:
            sec.add(HIGH, doc.rel, "スケルトンの記入例 `ADR-EX` が残っている", "削除する")
        leftovers = sorted(p for p in skeleton_placeholders(root, doc_id) if p in doc.text)
        if leftovers:
            sec.add(CHECK, doc.rel,
                    "スケルトンのプレースホルダが残っている可能性: {}{}".format(
                        " ".join(leftovers[:6]), " ほか" if len(leftovers) > 6 else ""),
                    "実内容に置き換える。意図して残す場合は理由を明記する")

        # (f) コードブロックの閉じ忘れ
        fences = sum(1 for ln in doc.lines if FENCE_RE.match(ln))
        if fences % 2 != 0:
            sec.add(MID, doc.rel, "コードブロック（```）の数が奇数で閉じ忘れの可能性がある")

        # (g) 章構成の欠落（テンプレート指定時は無視してよい）
        spec = DOC_SPECS.get(doc_id)
        if spec:
            skel_path = root / spec[1]
            if skel_path.is_file():
                skel_doc = Document(doc_id, skel_path, root)
                # 後フェーズで追記する章（SWP6の5〜6章等）は、この時点の欠落を欠陥としない
                expected = [h for h in skel_doc.headings(2) if "追記" not in h]
                actual = doc.headings(2)
                actual_norm = [re.sub(r"\s+", "", a) for a in actual]
                missing = [h for h in expected
                           if re.sub(r"\s+", "", h) not in actual_norm]
                if missing:
                    sec.add(CHECK, doc.rel,
                            "標準目次の章が見つからない: {}".format(" / ".join(missing[:6])),
                            "章を追加する。Product Ownerがテンプレートを指定した場合は本指摘を無視してよい")

    return sec


# ---------------------------------------------------------------------------
# チェック: ソースコード照合
# ---------------------------------------------------------------------------

def iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTS:
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        # リポジトリ内の相対パスだけを見る（ルートより上の階層名は判定に使わない）
        if set(relative.parts[:-1]) & SOURCE_EXCLUDE_DIRS:
            continue
        yield path


def declared_artifact_units(root: Path, sw205) -> list[dict]:
    """SW205で「成果物パス」を明示しているUNITを返す。

    エージェント定義開発では、ユニットの実装がリポジトリ直下のソースツリーではなく
    `.agents/` や `tools/` 配下（走査除外ディレクトリ）に置かれる。この場合は
    ソースツリーの走査ではなく、設計書が宣言したパスを直接照合する。
    従来型プログラム開発のSW205は「成果物パス」を持たないため、本関数は空を返し、
    照合の挙動は一切変わらない。
    """
    result = []
    for block in sw205.id_blocks("UNIT"):
        if block["id"].endswith("-EX"):
            continue
        declared = sw205.field_value(block, "成果物パス", "成果物ファイル").strip()
        if not declared:
            continue
        for token in re.split(r"[、,\s]+", declared.strip("`")):
            token = token.strip().strip("`").strip()
            if token:
                result.append({"id": block["id"], "path": token})
                break
    return result


def check_code(root: Path, docs: dict) -> Section:
    sec = Section("3. ソースコード照合（設計・テストとの対応）")
    sw205_doc = docs.get("SW205")
    declared = declared_artifact_units(root, sw205_doc) if sw205_doc is not None else []
    files = list(iter_source_files(root))
    if not files and not declared:
        sec.note("ソースコードが検出されなかった（Phase 4 開始前であれば正常）。")
        return sec
    sec.note("走査したソースファイル: {} 件".format(len(files)))
    if declared:
        sec.note("設計書が成果物パスを宣言したUNIT: {} 件（ソースツリー走査ではなく宣言パスを照合）"
                 .format(len(declared)))

    unit_hits: dict = {}
    tc_hits: dict = {}
    for path in files:
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        location = rel(root, path)
        for uid in collect_ids(text, "UNIT"):
            unit_hits.setdefault(uid, set()).add(location)
        for tid in collect_ids(text, "TC"):
            tc_hits.setdefault(tid, set()).add(location)
        for lineno, line in enumerate(text.split("\n"), start=1):
            for pattern, label in TAMPER_PATTERNS:
                if pattern.search(line):
                    sec.add(CHECK, "{}:{}".format(location, lineno),
                            "{} の可能性がある記述を検出".format(label),
                            "意図的なら理由をコメントで明記する。テストを通すための無効化は禁止")
                    break

    sw205 = sw205_doc
    if sw205 is not None:
        declared_map = {d["id"]: d["path"] for d in declared}
        for uid, decl_path in sorted(declared_map.items()):
            target = (root / decl_path).resolve()
            loc = "{} / {}".format(sw205.rel, uid)
            if not target.is_file():
                sec.add(HIGH, loc,
                        "設計書が宣言した成果物パスが存在しない: {}".format(decl_path),
                        "成果物を生成するか、設計書の成果物パスを実体に合わせる")
                continue
            try:
                body = target.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                sec.add(HIGH, loc,
                        "成果物パスのファイルを読み込めない: {}".format(decl_path),
                        "ファイルの権限・文字コードを確認する")
                continue
            if uid not in collect_ids(body, "UNIT"):
                sec.add(HIGH, loc,
                        "成果物 {} に対応UNIT-IDの記載がない".format(decl_path),
                        "ファイル冒頭（自然言語ならfrontmatter直後、コードならヘッダ）に対応IDを明記する")

        unit_ids = [b["id"] for b in sw205.id_blocks("UNIT") if not b["id"].endswith("-EX")]
        scan_ids = [u for u in unit_ids if u not in declared_map]
        missing = [u for u in scan_ids if u not in unit_hits]
        for u in missing:
            sec.add(HIGH, "{} / {}".format(sw205.rel, u),
                    "このUNIT-IDを参照するソースファイルがない（未実装、またはヘッダのID記載漏れ）",
                    "実装するか、ファイル・関数ヘッダに対応IDを明記する")
        if scan_ids:
            sec.note("UNIT↔コード 対応: {}/{} 件".format(len(scan_ids) - len(missing), len(scan_ids)))

    swp6 = docs.get("SWP6")
    if swp6 is not None:
        header, rows = swp6.tc_table()
        col_kind = swp6.column(header, "実行区分")
        auto_tcs = []
        for _, cells in rows:
            ids = normalize_id_list(cells[0], "TC")
            if not ids or ids[0].endswith("-EX"):
                continue
            kind = cells[col_kind] if 0 <= col_kind < len(cells) else ""
            if "自動" in kind:
                auto_tcs.append(ids[0])
        missing_tc = [t for t in auto_tcs if t not in tc_hits]
        for t in missing_tc:
            sec.add(MID, "{} / {}".format(swp6.rel, t),
                    "「自動」区分だがこのTC-IDを参照するテストコードがない",
                    "テストコードを実装し、コメントに対応TC-IDを明記する")
        if auto_tcs:
            sec.note("自動TC↔テストコード 対応: {}/{} 件".format(
                len(auto_tcs) - len(missing_tc), len(auto_tcs)))

    return sec


# ---------------------------------------------------------------------------
# チェック: 帳票の未解決件数
# ---------------------------------------------------------------------------

def check_status(root: Path) -> Section:
    sec = Section("4. 帳票の未解決状況（REV101 / BUG101）")
    art = root / "docs" / "artifacts"
    if not art.is_dir():
        sec.note("docs/artifacts が存在しない。")
        return sec

    targets = sorted(list(art.glob("REV101*.md")) + list(art.glob("BUG101*.md")))
    if not targets:
        sec.note("REV101 / BUG101 が見つからない。")
        return sec

    for path in targets:
        lines = read_lines(path)
        kinds = classify_lines(lines)
        open_rows = []
        for _, header, rows in iter_tables(lines, kinds):
            col_status = -1
            for idx, h in enumerate(header):
                if "ステータス" in h or "状態" in h:
                    col_status = idx
            if col_status < 0:
                continue
            for lineno, cells in rows:
                if col_status >= len(cells):
                    continue
                status = cells[col_status]
                first = cells[0] if cells else ""
                if not re.search(r"\b[RB]\d{1,4}\b", first):
                    continue
                if any(c.startswith(("(例", "（例", "例:", "例：")) for c in cells):
                    continue  # 帳票テンプレートの記入例行は数えない
                if status and ("Open" in status or "未" in status or "対応中" in status):
                    open_rows.append("{}({})".format(first, lineno))
        if open_rows:
            sec.add(CHECK, rel(root, path),
                    "未解決の行が {} 件ある: {}".format(len(open_rows), ", ".join(open_rows[:10])),
                    "対応してステータスを Closed / 解決済 にする。残す場合は承認ゲート報告で残課題として明示する")
        else:
            sec.note("{}: 未解決なし".format(rel(root, path)))
    return sec


# ---------------------------------------------------------------------------
# 実行
# ---------------------------------------------------------------------------

def load_docs(root: Path) -> dict:
    docs = {}
    for doc_id, (prefix, _) in DOC_SPECS.items():
        path = find_artifact(root, prefix)
        if path is not None:
            docs[doc_id] = Document(doc_id, path, root)
    return docs


def build_report(root: Path, command: str) -> tuple[str, str, dict]:
    docs = load_docs(root)
    sections = []
    if command in ("all", "trace"):
        sections.append(check_trace(root, docs))
    if command in ("all", "lint"):
        sections.append(check_lint(root, docs))
    if command in ("all", "code"):
        sections.append(check_code(root, docs))
    if command in ("all", "status"):
        sections.append(check_status(root))

    totals = {HIGH: 0, MID: 0, CHECK: 0}
    for sec in sections:
        for key, value in sec.counts().items():
            totals[key] = totals.get(key, 0) + value

    verdict = "NG（High指摘あり）" if totals[HIGH] else (
        "要対応（Mid指摘あり）" if totals[MID] else "OK")
    summary = "DADA-CHECK: {} | High {} / Mid {} / 要確認 {} | 対象: {}".format(
        verdict, totals[HIGH], totals[MID], totals[CHECK],
        ", ".join(sorted(docs)) or "文書未作成")

    header = [
        "# DADA 機械チェック結果",
        "",
        "- 実行日時: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "- 実行コマンド: `dada_check.py {}`".format(command),
        "- 判定: **{}**（High {} / Mid {} / 要確認 {}）".format(
            verdict, totals[HIGH], totals[MID], totals[CHECK]),
        "",
        "> High = 後工程を開始できない欠陥 / Mid = 品質を損なうが工程は進められる /"
        " 要確認 = 機械判定できないため人間またはAIの判断が必要。",
        "",
        "",
    ]
    body = "\n\n".join(sec.render() for sec in sections)
    return "\n".join(header) + body + "\n", summary, totals


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="DADAプロセスの開発文書とコードを機械的に検証する。")
    parser.add_argument("command", nargs="?", default="all",
                        choices=["all", "trace", "lint", "code", "status"])
    parser.add_argument("--root", default=None, help="リポジトリルート")
    parser.add_argument("--summary", action="store_true", help="サマリ1行のみ出力する")
    parser.add_argument("--no-report", action="store_true",
                        help="docs/process/check_report.md を書き出さない")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    if not root.is_dir():
        print("エラー: ルートディレクトリが見つからない: {}".format(root), file=sys.stderr)
        return 2

    report, summary, totals = build_report(root, args.command)

    if not args.no_report:
        out_dir = root / "docs" / "process"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "check_report.md").write_text(report, encoding="utf-8")
        except OSError as exc:
            print("警告: レポートを書き出せなかった: {}".format(exc), file=sys.stderr)

    if args.summary:
        print(summary)
    else:
        print(report)
        print(summary)
    return 1 if totals[HIGH] else 0


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
