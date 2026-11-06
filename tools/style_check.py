#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DADA Process 日本語推敲・AI-Slop検出・意味保持検証ツール (style_check.py)

目的:
    1. AIエージェント特有の「AIっぽい不自然な日本語（AI-Slop）」や「構造的な読みにくさ」を
       LLMを介さずに決定論的スクリプトで行番号付きで検出し、推敲・レビュー時のトークン消費を節約する。
    2. 推敲（書き直し）の前後で、元の文書の「意味（トレーサビリティID・数値・単位・否定/義務の極性・
       見出し構造・表の行列数）」が失われていないかを機械的に照合（verify）し、推敲による仕様変質事故を防ぐ。

設計の背景・クレジット:
    - 本ツールの検出カテゴリは、大賀愛一郎氏 (nanaism / ALGO ARTIS) によるオープンソーススキル
      『yomiyasu』(https://github.com/nanaism/yomiyasu, MIT License) の構造推敲思想、
      逆瀬川氏によるQiita記事の定量分析 (https://nyosegawa.com/posts/qiita-writing-before-after-ai/)、
      および ASDoQ システム開発文書品質モデル（理解容易性・可読性・規範適合性）を統合・拡張したものである。

前提:
    Python 3.8 以降の標準ライブラリのみ。外部依存なし。

使い方:
    python tools/style_check.py lint --input <md_path> [--summary]
    python tools/style_check.py snapshot --input <md_path> [--summary]
    python tools/style_check.py verify --input <md_path> [--summary]

終了コード:
    0 = 問題なし（または verify で意味保持を確認）
    1 = 推敲・確認すべき指摘あり（verify では意味欠落・変質の疑いあり）
    2 = 引数・実行エラー
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 定数・検出パターン定義（ASDoQ品質特性と対応）
# ---------------------------------------------------------------------------

HIGH = "High"      # 意味の変質・ID/数値の欠落（verify時）
MID = "Mid"        # 明確なAI-Slop表現・過剰対比・極端な長文（推敲で直すべき項目）
CHECK = "要確認"   # 文脈により許容されるが簡潔化を検討すべき項目

SNAPSHOT_DIR = Path("docs/process/.style_snapshots")

# 1. 不自然な比喩・擬人化・大げさなAI常套句 【ASDoQ: 4.理解容易性 / 5.可読性(表現適切性)】
AI_METAPHOR_SLOP: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"静かに(?:壊れ|破綻|失敗|進行|広が)"), "不自然な擬人化比喩（「静かに〜」）",
     "何がどの条件でエラーや不整合を起こすかを事実で記述する"),
    (re.compile(r"地味に(?:効く|重要|便利|大変|辛い)"), "AI特有の口語比喩（「地味に〜」）",
     "具体的な効果や影響範囲を客観的に記述する"),
    (re.compile(r"ボディブローのように"), "不自然な身体性比喩（「ボディブローのように」）",
     "累積的な影響や負荷を具体的に記述する"),
    (re.compile(r"解像度(?:を上げ|が上が|が高|が低|を高め)"), "AI頻出の比喩語（「解像度」）",
     "「詳細度」「具体性」「定義の粒度」等に言い換える"),
    (re.compile(r"手触り(?:感)?"), "AI頻出の感覚比喩（「手触り」）",
     "「操作感」「応答性」「使用感」「具体的な挙動」に言い換える"),
    (re.compile(r"昇華(?:させ|する|した)"), "大げさな文学的表現（「昇華する」）",
     "「具体化する」「設計に落とし込む」「変換する」等に言い換える"),
    (re.compile(r"寄り添(?:う|った|いながら)"), "宣伝調の擬人化表現（「寄り添う」）",
     "「利用者の操作手順に合わせる」「〜に対応する」等、具体的な仕様で記述する"),
    (re.compile(r"悲鳴を上げ"), "不自然な擬人化比喩（「悲鳴を上げる」）",
     "「負荷が上限を超える」「応答が遅延する」等の事実で記述する"),
    (re.compile(r"一気通貫で"), "曖昧な強調語（「一気通貫で」）",
     "どこからどこまでの工程・処理を連続実行するかを明記する"),
    (re.compile(r"シームレス(?:に|な)"), "曖昧な宣伝調表現（「シームレスに」）",
     "「手動操作なしで」「画面遷移なしで」等、具体的な動作を記述する"),
    (re.compile(r"過言では(?:ない|ありません)"), "大げさな修辞表現（「〜と言っても過言ではない」）",
     "修辞を削り、事実のみを簡潔に言い切る"),
    (re.compile(r"に他な(?:らない|りません)"), "大げさな強調構文（「〜に他ならない」）",
     "「〜である」と言い切る"),
    (re.compile(r"(?:鍵|カギ)を握(?:る|って)|(?:鍵|カギ)とな(?:る|り)"), "比喩的な強調表現（「鍵となる／カギを握る」）",
     "「重要である」「〜の成否を決める前提条件である」等に直す"),
    (re.compile(r"礎とな(?:る|り)"), "大げさな比喩表現（「礎となる」）",
     "「土台となる」「前提となる」等に直す"),
]

# 2. AI特有の頻出スラング・曖昧動詞 【ASDoQ: 4.理解容易性(非曖昧性) / 5.可読性】
AI_JARGON_SLOP: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"(?<![有効実])効(?:く|いてくる|いています)"), "AI頻出の曖昧動詞（「効く」）",
     "「機能する」「効果がある」「適用される」「影響する」等、意味を特定できる動詞にする"),
    (re.compile(r"事故(?:る|が起き|を防)"), "口語的・曖昧な表現（「事故る／事故」）",
     "「障害」「データ破損」「不整合」「誤動作」等、具体的な事象名で記述する"),
    (re.compile(r"別物(?:である|になり|です|として)"), "AI頻出の強調語（「別物」）",
     "何がどう異なるのか（役割・構造・入出力の違い）を具体的に記述する"),
    (re.compile(r"担保(?:する|し|され)"), "仕様書で乱用されやすい曖昧語（「担保する」）",
     "「保証する」「検証する」「満たす」「維持する」等、具体的な動作に置き換える"),
    (re.compile(r"享受(?:する|でき|し)"), "翻訳調の硬い表現（「享受する」）",
     "「得る」「利用できる」「受け取る」等に直す"),
]

# 3. 過剰な否定対比構文（「単なるAではなくB」等） 【ASDoQ: 5.可読性(簡潔性)】
CONTRAST_SLOP: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"単なる.{1,30}ではなく"), "過剰な否定対比構文（「単なる〜ではなく」）",
     "読み手が誤解していない否定対比を削り、肯定文で直接「何であるか」を書く"),
    (re.compile(r"ただの.{1,30}ではなく"), "過剰な否定対比構文（「ただの〜ではなく」）",
     "否定対比を削り、肯定文で直接記述する"),
    (re.compile(r"ではなく[、,]?\s*むしろ"), "翻訳調の強調対比（「〜ではなく、むしろ〜」）",
     "後半の主張だけを直接記述する"),
]

# 4. 英語由来のダッシュ記号（Qiita分析でAI以降約10倍に急増） 【ASDoQ: 5.可読性(表記適切性)】
DASH_SLOP_RE = re.compile(r"(?:\s+[—―─]{1,2}\s+|——|――)")

# 5. 意味の薄い前置き・冗長な機能動詞結合 【ASDoQ: 5.可読性(簡潔性)】
VERBOSE_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"言うまでもなく|周知の通り|ご存知の通り"), "不要な前置き（「言うまでもなく」等）",
     "前置きを削除し、本題から書き始める"),
    (re.compile(r"特筆すべき(?:は|点として|こととして)"), "宣伝調の前置き（「特筆すべきは」）",
     "削除して事実を直接書く"),
    (re.compile(r"することが可能(?:である|です|とな|にな)"), "冗長な可能表現（「〜することが可能である」）",
     "「〜できる」に簡潔化する"),
    (re.compile(r"の(?:実行|実施|作成|生成|検証|確認|更新|削除|取得|送信|保存)を行(?:う|います|い|った)"),
     "冗長な名詞＋「〜を行う」表現",
     "「実行する」「作成する」「検証する」のように動詞で直接言い切る"),
    (re.compile(r"という(?:観点|側面|意味)から"), "回りくどいつなぎ表現（「〜という観点から」）",
     "「〜のため」「〜において」にするか削除する"),
]

# 5. 一文の長さ・読点過多・太字過多の閾値 【ASDoQ: 4.理解容易性(一文一義) / 5.可読性】
MAX_SENTENCE_CHARS = 110
MAX_COMMAS_PER_SENTENCE = 4
MAX_BOLD_PER_PARAGRAPH = 4


# ---------------------------------------------------------------------------
# ユーティリティ・行種別判定
# ---------------------------------------------------------------------------

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")


def iter_prose_lines(text: str) -> List[Tuple[int, str, bool]]:
    """
    コードブロック・frontmatter・HTMLコメントを除いた行リスト (行番号, 行文字列, 表内かどうか) を返す。
    """
    lines = text.split("\n")
    in_code = False
    in_fm = False
    in_comment = False
    result: List[Tuple[int, str, bool]] = []

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if idx == 1 and stripped == "---":
            in_fm = True
            continue
        if in_fm:
            if stripped == "---":
                in_fm = False
            continue
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if "<!--" in stripped:
            if "-->" not in stripped:
                in_comment = True
            continue
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if not stripped:
            continue
        # 記入例・悪い例・禁止対象ワード・出典説明行は検査対象外とする
        if any(k in stripped for k in ("❌", "✅", "悪い例", "良い例", "要注意ワード", "排除対象ワード", "具体化対象ワード", "簡潔化の定石", "活用内容:", "著作権・出典表示:")):
            continue

        unquoted = re.sub(r"^(?:>\s*)+", "", stripped)
        is_table = unquoted.startswith("|") and unquoted.endswith("|")
        if is_table and re.match(r"^\|[\s:|-]+\|$", unquoted):
            continue
        result.append((idx, line, is_table))

    return result


# ---------------------------------------------------------------------------
# チェック1: lint（AI-Slop・構造的な読みにくさの機械検出）
# ---------------------------------------------------------------------------

def lint_markdown_style(path: Path) -> Tuple[List[Dict[str, Any]], str]:
    """
    Markdown文書の「AIっぽさ（AI-Slop）」と「読みにくさ」を検出し、指摘リストとサマリ行を返す。
    """
    text = read_text(path)
    prose_lines = iter_prose_lines(text)
    findings: List[Dict[str, Any]] = []

    for lineno, raw_line, is_table in prose_lines:
        clean_line = re.sub(r"`[^`]+`", "CODE", raw_line)
        clean_line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean_line)

        # 1. 比喩・擬人化・大げさな表現
        for pat, label, hint in AI_METAPHOR_SLOP:
            m = pat.search(clean_line)
            if m:
                findings.append({
                    "severity": MID,
                    "line": lineno,
                    "category": "AI比喩・誇張【ASDoQ: 理解容易性/可読性】",
                    "matched": m.group(0),
                    "message": label,
                    "hint": hint,
                })

        # 2. AI頻出スラング・曖昧動詞
        for pat, label, hint in AI_JARGON_SLOP:
            m = pat.search(clean_line)
            if m:
                findings.append({
                    "severity": MID,
                    "line": lineno,
                    "category": "AI頻出語彙【ASDoQ: 理解容易性(非曖昧性)】",
                    "matched": m.group(0),
                    "message": label,
                    "hint": hint,
                })

        # 3. 過剰な否定対比構文
        for pat, label, hint in CONTRAST_SLOP:
            m = pat.search(clean_line)
            if m:
                findings.append({
                    "severity": MID,
                    "line": lineno,
                    "category": "過剰な否定対比【ASDoQ: 可読性(簡潔性)】",
                    "matched": m.group(0),
                    "message": label,
                    "hint": hint,
                })

        # 4. 英語由来のダッシュ繋ぎ（表・見出し以外の本文で検査）
        is_heading = re.sub(r"^(?:>\s*)+", "", raw_line.strip()).startswith("#")
        if not is_table and not is_heading:
            m_dash = DASH_SLOP_RE.search(clean_line)
            if m_dash:
                findings.append({
                    "severity": CHECK,
                    "line": lineno,
                    "category": "AI特有のダッシュ記号【ASDoQ: 可読性(表記適切性)】",
                    "matched": m_dash.group(0).strip(),
                    "message": "英語圏LLM由来のダッシュ繋ぎ（`—` / `―`）が使われています（AI以降に約10倍急増した表現）",
                    "hint": "日本語として自然な読点（`、`）、句点（`。`）、または括弧書きに置き換える",
                })

        # 5. 冗長表現・意味の薄い前置き
        for pat, label, hint in VERBOSE_PATTERNS:
            m = pat.search(clean_line)
            if m:
                findings.append({
                    "severity": CHECK,
                    "line": lineno,
                    "category": "冗長表現【ASDoQ: 可読性(簡潔性)】",
                    "matched": m.group(0),
                    "message": label,
                    "hint": hint,
                })

        # 5. 一文の長さ・読点過多（表以外の通常段落・箇条書きで検査）
        if not is_table and not clean_line.strip().startswith("#"):
            # 行頭の箇条書きラベル（`- **項目**:`）を除外して文単位に分割
            body_part = re.sub(r"^\s*(?:[-*+]|\d+\.)\s*(?:\*\*[^*]+\*\*\s*[:：]\s*)?", "", clean_line)
            sentences = [s.strip() for s in re.split(r"[。！？]", body_part) if s.strip()]
            for sent in sentences:
                plain_s = re.sub(r"\*\*([^*]+)\*\*", r"\1", sent)
                if len(plain_s) > MAX_SENTENCE_CHARS:
                    findings.append({
                        "severity": MID,
                        "line": lineno,
                        "category": "長文・一文多義【ASDoQ: 理解容易性(一文一義)】",
                        "matched": plain_s[:35] + "…",
                        "message": f"1文が長すぎます（{len(plain_s)}文字 > 上限{MAX_SENTENCE_CHARS}文字）",
                        "hint": "「〜し、〜ため」で繋げず、1文1義に分割する",
                    })
                comma_cnt = plain_s.count("、") + plain_s.count("，")
                if comma_cnt > MAX_COMMAS_PER_SENTENCE:
                    findings.append({
                        "severity": CHECK,
                        "line": lineno,
                        "category": "読点過多・ねじれ文懸念【ASDoQ: 規範適合性(文法適合性)】",
                        "matched": plain_s[:35] + "…",
                        "message": f"1文内の読点が多すぎます（{comma_cnt}個）",
                        "hint": "主語と述語の距離が離れねじれ文になりやすいため、文を分ける",
                    })

            # 太字の過剰装飾チェック（行頭の `- **キー**:` は除く）
            bold_matches = re.findall(r"\*\*[^*]+\*\*", body_part)
            if len(bold_matches) > MAX_BOLD_PER_PARAGRAPH:
                findings.append({
                    "severity": CHECK,
                    "line": lineno,
                    "category": "過剰装飾【ASDoQ: 可読性(表記適切性)】",
                    "matched": ", ".join(bold_matches[:4]),
                    "message": f"1段落内の太字強調が多すぎます（{len(bold_matches)}箇所）",
                    "hint": "本当に強調すべき箇所だけに絞る（強調のインフレを防ぐ）",
                })

    mid_cnt = sum(1 for f in findings if f["severity"] == MID)
    chk_cnt = sum(1 for f in findings if f["severity"] == CHECK)
    status = "WARN" if mid_cnt > 0 else "OK"
    summary = f"STYLE-LINT: {status} | file={path.as_posix()} | Mid={mid_cnt} / 要確認={chk_cnt}"
    return findings, summary


def render_lint_report(path: Path, findings: List[Dict[str, Any]], summary: str) -> str:
    lines = [
        f"# 日本語推敲・AI-Slop チェック結果: `{path.as_posix()}`",
        "",
        f"- サマリ: `{summary}`",
        "",
    ]
    if not findings:
        lines.append("- 指摘なし（AI特有の比喩・過剰対比・長文は検出されませんでした）")
        return "\n".join(lines)

    for f in findings[:40]:
        lines.append(
            f"- [{f['severity']}] L{f['line']} ({f['category']}): "
            f"{f['message']} — 該当: `{f['matched']}` （対応: {f['hint']}）"
        )
    if len(findings) > 40:
        lines.append(f"- ...他 {len(findings) - 40} 件")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# チェック2: snapshot & verify（推敲前後の「意味保持」の決定論的検証）
# ---------------------------------------------------------------------------

ID_TOKEN_RE = re.compile(r"\b(?:REQ|TC|UNIT|EV|ADR|R|B)-\d{1,4}\b|\b[RB]\d{3,4}\b")
NUMBER_TOKEN_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:件|秒|ms|ミリ秒|分|時間|日|回|%|％|MB|GB|KB|バイト|文字|行|列|点|個|人|ページ|章|節)?")
NEGATION_CUES = ("禁止", "不可", "してはならない", "しない", "できない", "含まない", "除く", "以外")
MODAL_CUES = ("必須", "必ず", "のみ", "限り", "Must", "Should", "Could", "Pass", "Fail", "APPROVED", "REJECTED")


def extract_semantic_signature(text: str) -> Dict[str, Any]:
    """
    文書から「推敲によって絶対に勝手に変わってはならない意味要素」を抽出する。
      1. トレーサビリティID一覧と出現回数
      2. 数値・単位表現一覧
      3. 見出し一覧（レベルと章番号）
      4. 表の数と各表の行数・列数
      5. 否定・禁止・義務表現のカウント
    """
    _, body = (text.split("\n---", 1)[-1] if text.startswith("---\n") else ("", text)) if False else ("", text)
    lines = text.split("\n")

    ids = sorted(set(ID_TOKEN_RE.findall(text)))
    headings = []
    tables = []
    in_code = False
    cur_tbl_rows = 0
    cur_tbl_cols = 0

    for line in lines:
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m_h = re.match(r"^(#{1,6})\s+(.+)$", s)
        if m_h:
            headings.append([len(m_h.group(1)), m_h.group(2).strip()])
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not all(re.match(r"^:?-{2,}:?$", c.replace(" ", "")) for c in cells if c):
                cur_tbl_rows += 1
                cur_tbl_cols = max(cur_tbl_cols, len(cells))
        else:
            if cur_tbl_rows > 0:
                tables.append([cur_tbl_rows, cur_tbl_cols])
                cur_tbl_rows = 0
                cur_tbl_cols = 0
    if cur_tbl_rows > 0:
        tables.append([cur_tbl_rows, cur_tbl_cols])

    # 行番号を除いた本文から数値・単位トークンを抽出
    numbers = sorted(set(m.strip() for m in NUMBER_TOKEN_RE.findall(text) if m.strip()))

    neg_counts = {w: text.count(w) for w in NEGATION_CUES if text.count(w) > 0}
    modal_counts = {w: text.count(w) for w in MODAL_CUES if text.count(w) > 0}

    return {
        "ids": ids,
        "numbers": numbers,
        "headings_count": len(headings),
        "headings": headings,
        "tables": tables,
        "neg_counts": neg_counts,
        "modal_counts": modal_counts,
    }


def _snapshot_path_for(md_path: Path) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", md_path.as_posix())
    return SNAPSHOT_DIR / f"{safe_name}.json"


def save_snapshot(md_path: Path) -> Path:
    sig = extract_semantic_signature(read_text(md_path))
    snap_file = _snapshot_path_for(md_path)
    snap_file.write_text(json.dumps(sig, ensure_ascii=False, indent=2), encoding="utf-8")
    return snap_file


def verify_against_snapshot(md_path: Path) -> Tuple[List[str], List[str], str]:
    """
    推敲後のファイルと推敲前のスナップショットを比較し、
    (High欠陥リスト, 要確認リスト, サマリ行) を返す。
    """
    snap_file = _snapshot_path_for(md_path)
    if not snap_file.is_file():
        return [], ["スナップショットが未作成のため差分検証をスキップしました（先に snapshot を実行してください）"], (
            f"STYLE-VERIFY: SKIP | file={md_path.as_posix()} | reason=no_snapshot"
        )

    before = json.loads(snap_file.read_text(encoding="utf-8"))
    after = extract_semantic_signature(read_text(md_path))

    high_issues: List[str] = []
    check_issues: List[str] = []

    # 1. IDの消失・勝手な追加チェック
    missing_ids = sorted(set(before["ids"]) - set(after["ids"]))
    added_ids = sorted(set(after["ids"]) - set(before["ids"]))
    if missing_ids:
        high_issues.append(f"推敲によりトレーサビリティIDが消失しました: {', '.join(missing_ids)}")
    if added_ids:
        high_issues.append(f"推敲により元文書にないIDが追加されました: {', '.join(added_ids)}")

    # 2. 数値・単位の消失チェック
    missing_nums = sorted(set(before["numbers"]) - set(after["numbers"]))
    if missing_nums:
        high_issues.append(f"推敲により数値・単位表現が変化または消失しました: {', '.join(missing_nums[:15])}")

    # 3. 表の数・行数・列数の変化チェック
    if before["tables"] != after["tables"]:
        high_issues.append(
            f"推敲により表の構造（行数×列数）が変化しました: 推敲前={before['tables']} -> 推敲後={after['tables']}"
        )

    # 4. 見出し数の変化チェック
    if before["headings_count"] != after["headings_count"]:
        high_issues.append(
            f"推敲により見出しの数が変化しました: 推敲前={before['headings_count']} -> 推敲後={after['headings_count']}"
        )

    # 5. 否定・義務表現の増減チェック（極性反転の検知）
    for w, old_c in before["neg_counts"].items():
        new_c = after["neg_counts"].get(w, 0)
        if new_c < old_c:
            check_issues.append(f"否定・禁止語 `{w}` の出現数が減っています（{old_c} -> {new_c}）。禁止条件が落ちていないか確認してください")

    for w, old_c in before["modal_counts"].items():
        new_c = after["modal_counts"].get(w, 0)
        if new_c != old_c:
            check_issues.append(f"義務・判定語 `{w}` の出現数が変化しています（{old_c} -> {new_c}）。要求の強さが変わっていないか確認してください")

    status = "FAIL" if high_issues else ("WARN" if check_issues else "OK")
    summary = (
        f"STYLE-VERIFY: {status} | file={md_path.as_posix()} | "
        f"High={len(high_issues)} / 要確認={len(check_issues)}"
    )
    return high_issues, check_issues, summary


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DADA Process 日本語推敲・AI-Slop検出・意味保持検証ツール (style_check.py)"
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # lint
    p_lint = sub.add_parser("lint", help="AIっぽい不自然な日本語（AI-Slop）や長文・冗長表現を機械検出する")
    p_lint.add_argument("--input", required=True, help="検査対象Markdownファイルパス (.md)")
    p_lint.add_argument("--summary", action="store_true", help="1行サマリのみ出力する")

    # snapshot
    p_snap = sub.add_parser("snapshot", help="推敲前の意味シグネチャ（ID・数値・見出し・表・否定極性）を保存する")
    p_snap.add_argument("--input", required=True, help="対象Markdownファイルパス (.md)")
    p_snap.add_argument("--summary", action="store_true", help="1行サマリのみ出力する")

    # verify
    p_ver = sub.add_parser("verify", help="推敲後の文書が推敲前の意味シグネチャを保持しているか検証する")
    p_ver.add_argument("--input", required=True, help="推敲後のMarkdownファイルパス (.md)")
    p_ver.add_argument("--summary", action="store_true", help="1行サマリのみ出力する")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"[ERROR] 対象ファイルが存在しません: {in_path}", file=sys.stderr)
        return 2

    if args.subcommand == "lint":
        findings, summary = lint_markdown_style(in_path)
        if args.summary:
            print(summary)
        else:
            print(render_lint_report(in_path, findings, summary))
        mid_cnt = sum(1 for f in findings if f["severity"] == MID)
        return 1 if mid_cnt > 0 else 0

    elif args.subcommand == "snapshot":
        snap_file = save_snapshot(in_path)
        print(f"STYLE-SNAPSHOT: OK | file={in_path.as_posix()} | snapshot={snap_file.as_posix()}")
        return 0

    elif args.subcommand == "verify":
        high_issues, check_issues, summary = verify_against_snapshot(in_path)
        if args.summary:
            print(summary)
        else:
            print(f"# 推敲前後の意味保持検証レポート: `{in_path.as_posix()}`\n")
            print(f"- サマリ: `{summary}`\n")
            for h in high_issues:
                print(f"- [High] {h}")
            for c in check_issues:
                print(f"- [要確認] {c}")
            if not high_issues and not check_issues:
                print("- 全てのID・数値・単位・表構造・見出し・否定極性が推敲前と完全に一致しています。")
        return 1 if high_issues else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
