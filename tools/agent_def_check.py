#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DADA Process エージェント定義チェッカ (agent_def_check.py)

目的:
    開発対象が「エージェント定義」の場合に、自然言語レイヤー（SKILL.md / AGENTS.md /
    references）とプログラムレイヤー（tools 配下のスクリプト）の**一貫性**を機械的に検証する。
    `.agents/AGENTS.md` 第9節「自然言語とプログラム言語の一貫性遵守」のうち、
    機械で判定できる項目をAIの推論から本スクリプトへ委譲する。

    本スクリプトは `tools/dada_check.py` を変更・置換しない。両者は独立に実行する。
      - dada_check.py       : 開発文書のID対応・書き方・コードとの対応を検証する
      - agent_def_check.py  : エージェント定義そのものの構文と一貫性を検証する

検証する項目:
    1. frontmatter    : SKILL.md の name / description の存在、name とディレクトリ名の一致
    2. 参照パス       : 自然言語レイヤーが参照するファイルパスの実在（死リンクの検出）
    3. コマンド整合   : 手順に書かれたコマンド行が、実際のスクリプトの引数・オプションと一致するか
    4. 成果物パス     : SW205 の各 UNIT の「成果物パス」にファイルが存在し、UNIT-ID が記載されているか
    5. ポカヨケ       : 禁止事項の節、ループ上限の記述の有無（要確認として提示する）
    6. 評価セット     : SWP6 の評価ID（EV-xxx）が eval_report.md に記録されているか

前提:
    Python 3.8 以降の標準ライブラリのみ。外部依存なし。

使い方:
    python tools/agent_def_check.py            # 全チェック（推奨）
    python tools/agent_def_check.py skill      # frontmatter と参照パスのみ
    python tools/agent_def_check.py command    # コマンド整合のみ
    python tools/agent_def_check.py unit       # 成果物パスと UNIT-ID のみ
    python tools/agent_def_check.py eval       # 評価セットの記録のみ

    オプション:
      --root <path>    リポジトリルート（既定: 本スクリプトの親ディレクトリの親）
      --scan <path>    エージェント定義の走査対象ディレクトリ（既定: .agents。複数指定可）
      --summary        サマリ1行のみ出力する
      --no-report      docs/process/agent_def_check_report.md を書き出さない

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

DEFAULT_SCAN_DIRS = (".agents",)

# バッククォートで囲まれた文字列
INLINE_CODE_RE = re.compile(r"`([^`\n]{2,200})`")

# コマンド行（python / python3 / py -3 に続くスクリプト）
COMMAND_RE = re.compile(r"^(?:python3?|py\s+-3)\s+([\w./\\-]+\.py)(.*)$")

# 参照パスとして扱わない文字（プレースホルダ・グロブ・変数展開）
PATH_REJECT_CHARS = set("*<>{}|$?\"'()[]（）〈〉 \t")
PATH_REJECT_TOKENS = ("YYYY", "MM-DD", "…", "...", "例:", "例：", "ここに")

# 拡張子を持つパスのみ検証する（`references/` のような総称的なディレクトリ参照は対象外）
PATH_SUFFIX_RE = re.compile(r"\.[A-Za-z0-9]{1,5}$")

# プロセスの実行中に生成される成果物。存在しないことが正常なので実在確認の対象外とする
# （これらの実在は tools/dada_check.py が検証する）
OUTPUT_PATH_PREFIXES = ("docs/artifacts/",)

# 記入例・引用の行に現れるパスは、実在しないことが正常なので対象外とする
EXAMPLE_LINE_HINTS = ("記入例", "例:", "例：", "（例", "(例")

# frontmatter
FRONTMATTER_NAME_RE = re.compile(r"^name\s*:\s*(.+?)\s*$", re.MULTILINE)
FRONTMATTER_DESC_RE = re.compile(r"^description\s*:\s*(.+?)\s*$", re.MULTILINE)
SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")

# ID
UNIT_HEADING_RE = re.compile(r"^#{2,6}\s*(UNIT-(?:\d{1,4}|EX))\b")
UNIT_ID_RE = re.compile(r"\bUNIT-(?:\d{1,4}|EX)\b")
EV_ID_RE = re.compile(r"\bEV-(?:\d{1,4}|EX)\b")
FIELD_RE = re.compile(r"^\s*[-*+]\s*\*\*(.+?)\*\*\s*[:：]\s*(.*)$")

# ポカヨケの手掛かり
PROHIBITION_HINTS = ("禁止事項", "禁止する", "してはならない")
LOOP_HINTS = ("上限", "最大", "回まで", "回失敗", "打ち切")
LOOP_TRIGGERS = ("繰り返", "ループ", "反復", "再試行", "リトライ")


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
        self.findings = []
        self.notes = []

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
        ordered = sorted(self.findings,
                         key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.location))
        for f in ordered[:MAX_ITEMS_PER_CATEGORY]:
            lines.append(f.render())
        if len(ordered) > MAX_ITEMS_PER_CATEGORY:
            lines.append("- ...他 {} 件（同種の指摘。上記を直すと連鎖的に解消する場合が多い）".format(
                len(ordered) - MAX_ITEMS_PER_CATEGORY))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def iter_definition_files(root: Path, scan_dirs) -> list:
    """エージェント定義の自然言語レイヤーのファイルを列挙する。"""
    found = []
    for name in scan_dirs:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            found.append(path)
    return found


def looks_like_path(token: str) -> bool:
    token = token.strip()
    if not token or "/" not in token:
        return False
    if any(c in PATH_REJECT_CHARS for c in token):
        return False
    if any(t in token for t in PATH_REJECT_TOKENS):
        return False
    if token.startswith(("~", "/", "http://", "https://", "#")):
        return False
    if re.match(r"^[A-Za-z]:", token):
        return False
    # 「N/A」「REQ-001/REQ-002」のような列挙は除外する
    if re.match(r"^[A-Z]{2,4}-", token):
        return False
    return True


def is_checkable_reference(token: str) -> bool:
    """実在確認の対象とするパスかを判定する。"""
    if not looks_like_path(token):
        return False
    if not PATH_SUFFIX_RE.search(token):
        return False  # 総称的なディレクトリ参照（`references/` 等）
    if token.startswith(OUTPUT_PATH_PREFIXES):
        return False  # プロセスが後から生成する成果物
    return True


def resolve_reference(root: Path, base_dir: Path, token: str) -> bool:
    """参照パスが実在するかを判定する。ルート相対と、記述ファイルからの相対の両方を試す。"""
    for candidate in (root / token, base_dir / token):
        if candidate.exists():
            return True
    return False


def extract_frontmatter(text: str):
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    return text[3:end]


# ---------------------------------------------------------------------------
# チェック1: frontmatter と参照パス
# ---------------------------------------------------------------------------

def check_skill(root: Path, files: list) -> Section:
    sec = Section("1. 自然言語レイヤーの構文と参照パス")
    if not files:
        sec.note("走査対象のMarkdownファイルが見つからなかった（`--scan` の指定を確認する）。")
        return sec

    skill_files = [p for p in files if p.name == "SKILL.md"]
    sec.note("走査したファイル: {} 件（うち SKILL.md: {} 件）".format(len(files), len(skill_files)))

    # --- frontmatter ---
    for path in skill_files:
        loc = rel(root, path)
        text = read_text(path)
        fm = extract_frontmatter(text)
        if fm is None:
            sec.add(HIGH, loc, "frontmatter（先頭の `---` で囲むブロック）がない",
                    "先頭に `---` / `name:` / `description:` / `---` を置く")
            continue
        name_match = FRONTMATTER_NAME_RE.search(fm)
        desc_match = FRONTMATTER_DESC_RE.search(fm)
        if name_match is None:
            sec.add(HIGH, loc, "frontmatter に `name` がない",
                    "ディレクトリ名と同じ名前を `name` に書く")
        else:
            name = name_match.group(1).strip().strip("\"'")
            dir_name = path.parent.name
            if name != dir_name:
                sec.add(HIGH, loc,
                        "frontmatter の `name`（{}）がディレクトリ名（{}）と一致しない".format(name, dir_name),
                        "どちらかを他方に合わせる（スキルが発動しない原因になる）")
            elif not SKILL_NAME_RE.match(name):
                sec.add(MID, loc, "`name`（{}）が英小文字とハイフンのみで書かれていない".format(name))
        if desc_match is None:
            sec.add(HIGH, loc, "frontmatter に `description` がない",
                    "「いつ使うか」を先頭に書く（エージェントは description だけを見て発動を判断する）")
        else:
            desc = desc_match.group(1).strip().strip("\"'")
            if len(desc) < 20:
                sec.add(MID, loc, "`description` が短く発動条件を判断できない（{} 文字）".format(len(desc)),
                        "「〜するときに使用します」の形で発動条件を書く")

    # --- 参照パスの実在 ---
    for path in files:
        loc_base = rel(root, path)
        text = read_text(path)
        seen = set()
        for lineno, line in enumerate(text.split("\n"), start=1):
            if any(h in line for h in EXAMPLE_LINE_HINTS):
                continue  # 記入例の行に現れるパスは実在しないことが正常
            for token in INLINE_CODE_RE.findall(line):
                token = token.strip()
                if COMMAND_RE.match(token):
                    continue  # コマンドはチェック2で扱う
                if not is_checkable_reference(token):
                    continue
                if token in seen:
                    continue
                seen.add(token)
                if resolve_reference(root, path.parent, token):
                    continue
                # 親ディレクトリが実在する参照は「生きているはずのパス」なので重く扱う
                severity = HIGH if (root / token).parent.is_dir() else MID
                sec.add(severity, "{}:{}".format(loc_base, lineno),
                        "参照先が存在しない: `{}`".format(token),
                        "パスを修正するか、参照先のファイルを作成する（死んだ参照はエージェントの停止か推測を招く）")

    return sec


# ---------------------------------------------------------------------------
# チェック2: コマンド整合（手順とツールの引数の一致）
# ---------------------------------------------------------------------------

def check_command(root: Path, files: list) -> Section:
    sec = Section("2. コマンド整合（手順とツールの引数の一致）")
    scripts = {}
    total = 0

    for path in files:
        loc_base = rel(root, path)
        text = read_text(path)
        for lineno, line in enumerate(text.split("\n"), start=1):
            for token in INLINE_CODE_RE.findall(line):
                m = COMMAND_RE.match(token.strip())
                if not m:
                    continue
                total += 1
                script_rel, rest = m.group(1), m.group(2)
                loc = "{}:{}".format(loc_base, lineno)
                script_path = root / script_rel
                if not script_path.is_file():
                    sec.add(HIGH, loc,
                            "手順が参照するスクリプトが存在しない: `{}`".format(script_rel),
                            "スクリプトを実装するか、手順のパスを修正する")
                    continue
                if script_rel not in scripts:
                    scripts[script_rel] = read_text(script_path)
                body = scripts[script_rel]
                for opt in re.findall(r"--[A-Za-z][\w-]*", rest):
                    if opt not in body:
                        sec.add(HIGH, loc,
                                "スクリプト `{}` に存在しないオプション `{}` を手順が指定している".format(
                                    script_rel, opt),
                                "スクリプトの引数定義と手順のコマンド行を一致させる")
                for word in rest.split():
                    if word.startswith("-") or not re.match(r"^[a-z][a-z0-9_-]*$", word):
                        continue
                    if ('"{}"'.format(word) not in body) and ("'{}'".format(word) not in body):
                        sec.add(MID, loc,
                                "スクリプト `{}` に見つからないサブコマンド `{}` を手順が指定している".format(
                                    script_rel, word),
                                "スクリプトのサブコマンド定義と手順を一致させる（誤りでない場合は本指摘を棄却してよい）")

    if total == 0:
        sec.note("手順内にコマンド行が見つからなかった（プログラムレイヤーを持たない場合は正常）。")
    else:
        sec.note("照合したコマンド行: {} 件 / 参照されたスクリプト: {} 件".format(total, len(scripts)))
    return sec


# ---------------------------------------------------------------------------
# チェック3: 成果物パスと UNIT-ID
# ---------------------------------------------------------------------------

def find_artifact(root: Path, prefix: str):
    art_dir = root / "docs" / "artifacts"
    if not art_dir.is_dir():
        return None
    candidates = sorted(p for p in art_dir.glob("*.md") if p.name.startswith(prefix))
    return candidates[0] if candidates else None


def check_unit(root: Path) -> Section:
    sec = Section("3. 成果物パスと UNIT-ID の対応")
    sw205 = find_artifact(root, "SW205")
    if sw205 is None:
        sec.note("SW205 が未作成のためスキップした（Phase 3 開始前であれば正常）。")
        return sec

    lines = read_text(sw205).split("\n")
    loc205 = rel(root, sw205)
    blocks = []
    current = None
    for i, line in enumerate(lines):
        m = UNIT_HEADING_RE.match(line)
        if m:
            current = {"id": m.group(1), "lineno": i + 1, "fields": {}}
            blocks.append(current)
            continue
        if line.startswith("#") and current is not None:
            current = None
            continue
        if current is not None:
            fm = FIELD_RE.match(line)
            if fm:
                current["fields"][fm.group(1).strip()] = fm.group(2).strip()

    blocks = [b for b in blocks if not b["id"].endswith("-EX")]
    if not blocks:
        sec.note("SW205 に UNIT-ID の定義ブロックが見つからなかった。")
        return sec
    sec.note("SW205 の UNIT-ID: {} 件".format(len(blocks)))

    missing_layer = 0
    for block in blocks:
        loc = "{}:{} / {}".format(loc205, block["lineno"], block["id"])
        fields = block["fields"]
        layer = next((v for k, v in fields.items() if "レイヤー" in k), "")
        if not layer:
            missing_layer += 1
        raw = next((v for k, v in fields.items() if "成果物パス" in k), "")
        if not raw:
            sec.add(MID, loc, "「成果物パス」が未記入のため、実装漏れを機械的に検出できない",
                    "生成するファイルのパスを1件書く（1ユニット＝1ファイルを原則とする）")
            continue
        candidates = [t.strip() for t in INLINE_CODE_RE.findall(raw)] or [raw.strip()]
        for token in candidates:
            if not looks_like_path(token):
                continue
            target = root / token
            if not target.exists():
                sec.add(HIGH, loc, "成果物パスにファイルが存在しない: `{}`".format(token),
                        "実装するか、SW205の成果物パスを修正する（Phase 4 開始前であれば正常）")
                continue
            if target.is_file() and block["id"] not in read_text(target):
                sec.add(HIGH, loc,
                        "生成物 `{}` に対応 UNIT-ID の記載がない".format(token),
                        "ファイルヘッダまたは冒頭の注記に UNIT-ID を明記する（実装漏れ検出の根拠になる）")

    if missing_layer:
        sec.add(MID, loc205, "「レイヤー」が未記入のユニットが {} 件ある".format(missing_layer),
                "自然言語 / プログラム のいずれかを明記する")
    return sec


# ---------------------------------------------------------------------------
# チェック4: 評価セットの記録
# ---------------------------------------------------------------------------

def check_eval(root: Path) -> Section:
    sec = Section("4. 評価セット（Eval Dataset）の記録")
    swp6 = find_artifact(root, "SWP6")
    if swp6 is None:
        sec.note("SWP6 が未作成のためスキップした（Phase 2 開始前であれば正常）。")
        return sec

    swp6_text = read_text(swp6)
    ev_ids = sorted({m.group(0) for m in EV_ID_RE.finditer(swp6_text)
                     if not m.group(0).endswith("-EX")})
    has_eval_kind = "評価" in swp6_text

    if not ev_ids:
        if has_eval_kind:
            sec.add(MID, rel(root, swp6),
                    "実行区分「評価」の記述があるが、評価ID（`EV-001` 形式）が定義されていない",
                    "4.3節の評価セット定義表に評価IDを作り、対応TCと紐づける")
        else:
            sec.note("評価IDが未定義（従来型プログラム、または評価セットを使わない場合は正常）。")
        return sec

    sec.note("SWP6 の評価ID: {} 件".format(len(ev_ids)))

    report = root / "docs" / "process" / "eval_report.md"
    if not report.is_file():
        sec.add(MID, "docs/process/eval_report.md",
                "評価結果の記録ファイルが存在しない",
                "Phase 4で評価を実行し、試行ごとの結果を記録する（Phase 4 開始前であれば正常）")
        return sec

    report_text = read_text(report)
    unrecorded = [e for e in ev_ids if e not in report_text]
    for e in unrecorded:
        sec.add(MID, "docs/process/eval_report.md / {}".format(e),
                "この評価IDの実行結果が記録されていない",
                "評価を実行して合格率を記録する（Phase 4 開始前であれば正常）")
    if not unrecorded:
        sec.note("全評価IDが eval_report.md に記録済み。")
    if re.search(r"\|\s*1\s*回\s*\|", report_text):
        sec.add(CHECK, "docs/process/eval_report.md",
                "試行回数が1回の記録がある可能性がある",
                "1回の成功は確率的振る舞いの証明にならない。SWP6で定義した回数を実施する")
    return sec


# ---------------------------------------------------------------------------
# チェック5: ポカヨケ（要確認レベル）
# ---------------------------------------------------------------------------

def check_pokayoke(root: Path, files: list) -> Section:
    sec = Section("5. ポカヨケの作り込み（要確認）")
    skill_files = [p for p in files if p.name == "SKILL.md"]
    if not skill_files:
        sec.note("SKILL.md が見つからなかった。")
        return sec

    for path in skill_files:
        loc = rel(root, path)
        text = read_text(path)
        if not any(h in text for h in PROHIBITION_HINTS):
            sec.add(CHECK, loc, "「禁止事項」に相当する記述が見つからない",
                    "やってはならないことを独立した節に列挙する（逸脱の防止）")
        if any(t in text for t in LOOP_TRIGGERS) and not any(h in text for h in LOOP_HINTS):
            sec.add(CHECK, loc, "反復処理の記述があるが、上限回数と打ち切り後の行き先が見つからない",
                    "上限回数と、打ち切った後に誰へ報告するかを書く（停止しないループの防止）")
    if not sec.findings:
        sec.note("禁止事項とループ上限の記述を確認した。")
    return sec


# ---------------------------------------------------------------------------
# 実行
# ---------------------------------------------------------------------------

def build_report(root: Path, command: str, scan_dirs) -> tuple:
    files = iter_definition_files(root, scan_dirs)
    sections = []
    if command in ("all", "skill"):
        sections.append(check_skill(root, files))
    if command in ("all", "command"):
        sections.append(check_command(root, files))
    if command in ("all", "unit"):
        sections.append(check_unit(root))
    if command in ("all", "eval"):
        sections.append(check_eval(root))
    if command in ("all", "skill"):
        sections.append(check_pokayoke(root, files))

    totals = {HIGH: 0, MID: 0, CHECK: 0}
    for sec in sections:
        for key, value in sec.counts().items():
            totals[key] = totals.get(key, 0) + value

    verdict = "NG（High指摘あり）" if totals[HIGH] else (
        "要対応（Mid指摘あり）" if totals[MID] else "OK")
    summary = "AGENT-DEF-CHECK: {} | High {} / Mid {} / 要確認 {} | 走査: {} ファイル".format(
        verdict, totals[HIGH], totals[MID], totals[CHECK], len(files))

    header = [
        "# エージェント定義チェック結果",
        "",
        "- 実行日時: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "- 実行コマンド: `agent_def_check.py {}`".format(command),
        "- 走査対象: {}".format(", ".join(scan_dirs)),
        "- 判定: **{}**（High {} / Mid {} / 要確認 {}）".format(
            verdict, totals[HIGH], totals[MID], totals[CHECK]),
        "",
        "> High = 一貫性が破れており、エージェントが誤動作または停止する欠陥 /"
        " Mid = 品質を損なうが動作する / 要確認 = 機械判定できないため人間またはAIの判断が必要。",
        "",
        "",
    ]
    body = "\n\n".join(sec.render() for sec in sections)
    return "\n".join(header) + body + "\n", summary, totals


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="エージェント定義（スキル・ルール・知識＋ツール）の構文と一貫性を検証する。")
    parser.add_argument("command", nargs="?", default="all",
                        choices=["all", "skill", "command", "unit", "eval"])
    parser.add_argument("--root", default=None, help="リポジトリルート")
    parser.add_argument("--scan", action="append", default=None,
                        help="走査対象ディレクトリ（既定: .agents。複数指定可）")
    parser.add_argument("--summary", action="store_true", help="サマリ1行のみ出力する")
    parser.add_argument("--no-report", action="store_true",
                        help="docs/process/agent_def_check_report.md を書き出さない")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    if not root.is_dir():
        print("エラー: ルートディレクトリが見つからない: {}".format(root), file=sys.stderr)
        return 2

    scan_dirs = args.scan if args.scan else list(DEFAULT_SCAN_DIRS)
    report, summary, totals = build_report(root, args.command, scan_dirs)

    if not args.no_report:
        out_dir = root / "docs" / "process"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "agent_def_check_report.md").write_text(report, encoding="utf-8")
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
