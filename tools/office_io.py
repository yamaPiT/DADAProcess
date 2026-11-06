#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DADA Process Office文書・PDF 決定論的入出力ツール (office_io.py)

目的:
    1. DADAプロセスの「Markdownコア（Single Source of Truth）＋ オンデマンドOffice変換」を
       LLMを介さずに決定論的スクリプトとして実行し、トークン消費量を最小化する。
    2. 標準テンプレート（Word: `Normal.dotm` / PowerPoint: `Blank.potx` / Excel: `template_sheet.xlsx`）
       またはユーザー指定テンプレートのスタイル・余白・見出し番号・スライドマスターを厳密に保持する。
    3. 既存のOffice資産（.docx / .xlsx / .pptx / .pdf）からのMarkdown抽出（import）と、
       既存書式・数式・レイアウトを壊さない差分反映（patch）を提供する。

サブコマンド:
    python tools/office_io.py init-templates [--out-dir docs/templates/office]
    python tools/office_io.py import       --input <office_or_pdf> --output <md_path> [--summary]
    python tools/office_io.py export       --input <md_path> --output <office_or_pdf> [--template <tpl_path>] [--title <title>] [--summary]
    python tools/office_io.py patch        --base <existing_office> --input <updated_md> --output <out_office> [--summary]
    python tools/office_io.py batch-export [--artifacts-dir docs/artifacts] [--out-dir docs/artifacts/office] [--formats docx,xlsx,pdf] [--summary]
    python tools/office_io.py inspect      --input <office_or_pdf> [--summary]

終了コード:
    0 = 成功（High指摘なし） / 1 = 構造・レイアウト上の警告あり / 2 = 引数・実行エラー
"""

from __future__ import annotations

import argparse
import copy
import io
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 定数・既定テンプレートパス
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATE_DIR = Path("docs/templates/office")

# Word既定テンプレート: Normal.dotm を最優先し、無ければ template_document.docx を使用する
DEFAULT_WORD_DOTM = DEFAULT_TEMPLATE_DIR / "Normal.dotm"
DEFAULT_DOCX_TEMPLATE = DEFAULT_TEMPLATE_DIR / "template_document.docx"

# PowerPoint既定テンプレート: Blank.potx を最優先し、無ければ template_slide.pptx を使用する
DEFAULT_PPT_POTX = DEFAULT_TEMPLATE_DIR / "Blank.potx"
DEFAULT_PPTX_TEMPLATE = DEFAULT_TEMPLATE_DIR / "template_slide.pptx"

# Excel既定テンプレート
DEFAULT_XLSX_TEMPLATE = DEFAULT_TEMPLATE_DIR / "template_sheet.xlsx"

FONT_JA_WORD_BODY = "ＭＳ 明朝"
FONT_EN_WORD_BODY = "Century"
FONT_JA_WORD_HEAD = "ＭＳ ゴシック"
FONT_EN_WORD_HEAD = "Arial"
FONT_JA_SANS = "游ゴシック"
FONT_JA_PRESENTATION = "メイリオ"
FONT_EN_PRESENTATION = "Arial"
FONT_MONO = "Consolas"

COLOR_PRIMARY = (27, 54, 93)       # #1B365D 濃紺
COLOR_SECONDARY = (44, 82, 130)    # #2C5282 中紺
COLOR_TEXT = (0, 0, 0)             # #000000 黒（Normal.dotm / Blank.potx 準拠）
COLOR_MUTED = (108, 117, 125)      # #6C757D グレー
COLOR_BG_LIGHT = (244, 246, 249)   # #F4F6F9 薄グレー背景
COLOR_BORDER = (160, 160, 160)     # #A0A0A0 表罫線

# スライド1枚あたりの推奨上限（inspectでのレイアウト溢れ検出用）
MAX_SLIDE_BULLETS = 8
MAX_SLIDE_CHARS = 450
MAX_SLIDE_TABLE_ROWS = 10


# ---------------------------------------------------------------------------
# OpenXML テンプレート (.dotm / .dotx / .potx / .potm) ストリーム変換
# ---------------------------------------------------------------------------

WORD_TEMPLATE_CTS = (
    b"application/vnd.ms-word.template.macroEnabledTemplate.main+xml",
    b"application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
)
WORD_DOC_CT = b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"

PPT_TEMPLATE_CTS = (
    b"application/vnd.openxmlformats-officedocument.presentationml.template.main+xml",
    b"application/vnd.ms-powerpoint.template.macroEnabled.main+xml",
)
PPT_PRES_CT = b"application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"


def _load_template_as_document_stream(tpl_path: Path, is_word: bool) -> io.BytesIO:
    """
    .dotm / .dotx / .potx / .potm 等のOpenXMLテンプレートをメモリ上で
    通常ドキュメントのContentTypeに正規化し、python-docx / python-pptx で直接開けるBytesIOを返す。
    """
    buf = io.BytesIO()
    old_cts = WORD_TEMPLATE_CTS if is_word else PPT_TEMPLATE_CTS
    new_ct = WORD_DOC_CT if is_word else PPT_PRES_CT

    with zipfile.ZipFile(str(tpl_path), "r") as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "[Content_Types].xml":
                for old_ct in old_cts:
                    data = data.replace(old_ct, new_ct)
            zout.writestr(item, data)
    buf.seek(0)
    return buf


def resolve_word_template(custom_tpl: Optional[Path] = None) -> Optional[Path]:
    """使用するWordテンプレートのパスを決定する（Normal.dotm 優先）。"""
    if custom_tpl and custom_tpl.is_file():
        return custom_tpl
    if DEFAULT_WORD_DOTM.is_file():
        return DEFAULT_WORD_DOTM
    if DEFAULT_DOCX_TEMPLATE.is_file():
        return DEFAULT_DOCX_TEMPLATE
    return None


def resolve_ppt_template(custom_tpl: Optional[Path] = None) -> Optional[Path]:
    """使用するPowerPointテンプレートのパスを決定する（Blank.potx 優先）。"""
    if custom_tpl and custom_tpl.is_file():
        return custom_tpl
    if DEFAULT_PPT_POTX.is_file():
        return DEFAULT_PPT_POTX
    if DEFAULT_PPTX_TEMPLATE.is_file():
        return DEFAULT_PPTX_TEMPLATE
    return None


# ---------------------------------------------------------------------------
# Markdown パーサ（見出し・段落・リスト・表・コードブロック・ノート）
# ---------------------------------------------------------------------------

class MdBlock:
    """Markdownの1構造ブロックを表す。"""

    def __init__(self, kind: str, text: str = "", level: int = 0,
                 rows: Optional[List[List[str]]] = None,
                 items: Optional[List[Tuple[int, str, bool]]] = None,
                 meta: Optional[Dict[str, str]] = None):
        self.kind = kind          # heading / paragraph / list / table / code / rule / note
        self.text = text
        self.level = level        # heading: 1..6
        self.rows = rows or []    # table: List[List[str]] (先頭行はヘッダ)
        self.items = items or []  # list: List[(indent_level, text, is_ordered)]
        self.meta = meta or {}


def strip_frontmatter(md_text: str) -> Tuple[Dict[str, str], str]:
    """YAML frontmatter と HTMLコメントメタデータを抽出・除去する。"""
    meta: Dict[str, str] = {}
    text = md_text.replace("\r\n", "\n")

    for m in re.finditer(r"<!--\s*([a-zA-Z0-9_-]+)\s*:\s*(.+?)\s*-->", text):
        meta[m.group(1).strip()] = m.group(2).strip()

    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            fm_block = text[4:end]
            for line in fm_block.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip("\"'")
            text = text[end + 4:].lstrip("\n")

    cleaned_lines = []
    for line in text.split("\n"):
        if re.match(r"^\s*<!--.*-->\s*$", line):
            continue
        cleaned_lines.append(line)
    return meta, "\n".join(cleaned_lines)


def parse_markdown(md_text: str) -> Tuple[Dict[str, str], List[MdBlock]]:
    """Markdownテキストを構造ブロック列に変換する。"""
    meta, body = strip_frontmatter(md_text)
    lines = body.split("\n")
    blocks: List[MdBlock] = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if re.match(r"^(\*{3,}|-{3,}|_{3,})\s*$", stripped):
            blocks.append(MdBlock("rule"))
            i += 1
            continue

        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1
            blocks.append(MdBlock("code", text="\n".join(code_lines), meta={"lang": lang}))
            continue

        m_head = re.match(r"^(#{1,6})\s+(.+?)\s*$", stripped)
        if m_head:
            level = len(m_head.group(1))
            blocks.append(MdBlock("heading", text=m_head.group(2), level=level))
            i += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines = []
            while i < n and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            rows: List[List[str]] = []
            for idx, tline in enumerate(table_lines):
                cells = [c.strip() for c in tline.strip("|").split("|")]
                if idx == 1 and all(re.match(r"^:?-{2,}:?$", c.replace(" ", "")) for c in cells if c):
                    continue
                rows.append(cells)
            if rows:
                blocks.append(MdBlock("table", rows=rows))
            continue

        if stripped.startswith(">"):
            quote_lines = []
            while i < n and lines[i].strip().startswith(">"):
                q = re.sub(r"^>\s?", "", lines[i].strip())
                q = re.sub(r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*", r"【\1】 ", q)
                if q:
                    quote_lines.append(q)
                i += 1
            if quote_lines:
                blocks.append(MdBlock("note", text="\n".join(quote_lines)))
            continue

        m_ul = re.match(r"^(\s*)([-*+])\s+(.+)$", line)
        m_ol = re.match(r"^(\s*)(\d+\.)\s+(.+)$", line)
        if m_ul or m_ol:
            items: List[Tuple[int, str, bool]] = []
            while i < n:
                l_ul = re.match(r"^(\s*)([-*+])\s+(.+)$", lines[i])
                l_ol = re.match(r"^(\s*)(\d+\.)\s+(.+)$", lines[i])
                if l_ul:
                    indent = len(l_ul.group(1).expandtabs(2)) // 2
                    items.append((indent, l_ul.group(3).strip(), False))
                    i += 1
                elif l_ol:
                    indent = len(l_ol.group(1).expandtabs(2)) // 2
                    items.append((indent, l_ol.group(3).strip(), True))
                    i += 1
                else:
                    break
            blocks.append(MdBlock("list", items=items))
            continue

        para_lines = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith(("#", "|", "```", ">", "---", "***"))
                    or re.match(r"^(\s*)([-*+]|\d+\.)\s+", lines[i])):
                break
            para_lines.append(nxt)
            i += 1
        blocks.append(MdBlock("paragraph", text=" ".join(para_lines)))

    return meta, blocks


def clean_inline_md(text: str) -> str:
    """インラインMarkdown記法を除去する。"""
    s = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return s.strip()


def strip_heading_number(text: str) -> str:
    """
    テンプレート側（Normal.dotm等）の見出しスタイルに自動番号（1. / 1.1 / 1.1.1 / (1) 等）が
    設定されている場合に二重採番を防ぐため、Markdown見出し先頭の章番号を除去する。
    """
    s = clean_inline_md(text)
    s = re.sub(r"^(?:第\s*\d+\s*[章節項]\s*|\(\d+\)\s*(?:\d+\.)*\s*|\d+(?:\.\d+)*\.?\s+)", "", s)
    return s.strip() or clean_inline_md(text)


# ---------------------------------------------------------------------------
# Mermaid 図パーサ & 2D自動レイアウトエンジン（編集可能なネイティブOffice図形変換用）
# ---------------------------------------------------------------------------

def _clean_mermaid_label(raw: str) -> str:
    s = raw.strip().strip("\"'")
    s = s.replace("<br/>", "\n").replace("<br />", "\n").replace("<br>", "\n")
    s = re.sub(r"</?[^>]+>", "", s)
    return s.strip()


def _parse_mermaid_node_token(token: str, nodes: Dict[str, Dict[str, str]], order: List[str]) -> Optional[str]:
    """Mermaidのノードトークン（例: `A["要求定義"]`, `G{"判定"}`, `DB[("SW105")]`, `[*]`）を解析して登録する。"""
    t = token.strip()
    if not t:
        return None
    if t == "[*]":
        nid = "__STAR__"
        if nid not in nodes:
            nodes[nid] = {"id": nid, "label": "開始/終了", "shape": "oval"}
            order.append(nid)
        return nid

    patterns = [
        (r'^([A-Za-z0-9_.\-]+)\s*\(\[\s*(.+?)\s*\]\)$', "round"),
        (r'^([A-Za-z0-9_.\-]+)\s*\[\(\s*(.+?)\s*\)\]$', "cylinder"),
        (r'^([A-Za-z0-9_.\-]+)\s*\(\(\s*(.+?)\s*\)\)$', "oval"),
        (r'^([A-Za-z0-9_.\-]+)\s*\{\{\s*(.+?)\s*\}\}$', "diamond"),
        (r'^([A-Za-z0-9_.\-]+)\s*\{\s*(.+?)\s*\}$', "diamond"),
        (r'^([A-Za-z0-9_.\-]+)\s*\[\s*(.+?)\s*\]$', "rect"),
        (r'^([A-Za-z0-9_.\-]+)\s*\(\s*(.+?)\s*\)$', "round"),
    ]
    for pat, shp in patterns:
        m = re.match(pat, t)
        if m:
            nid = m.group(1).strip()
            lbl = _clean_mermaid_label(m.group(2))
            if nid not in nodes:
                nodes[nid] = {"id": nid, "label": lbl or nid, "shape": shp}
                order.append(nid)
            else:
                if lbl and nodes[nid]["label"] == nid:
                    nodes[nid]["label"] = lbl
                    nodes[nid]["shape"] = shp
            return nid

    m_id = re.match(r'^([A-Za-z0-9_.\-]+)$', t)
    if m_id:
        nid = m_id.group(1)
        if nid not in nodes:
            nodes[nid] = {"id": nid, "label": nid, "shape": "rect"}
            order.append(nid)
        return nid
    return None


def parse_mermaid_diagram(mermaid_code: str) -> Dict[str, Any]:
    """
    Mermaid記法（flowchart / graph / sequenceDiagram / stateDiagram / erDiagram / classDiagram）を解析し、
    ノードとエッジ（またはシーケンスの参加者とメッセージ）の構造データを返す。
    """
    raw_lines = mermaid_code.replace("\r\n", "\n").split("\n")
    lines: List[str] = []
    for ln in raw_lines:
        s = ln.strip()
        if not s or s.startswith("%%"):
            continue
        if re.match(r"^(classDef|class|style|linkStyle|click|direction)\b", s):
            continue
        lines.append(s)

    if not lines:
        return {"kind": "empty", "direction": "TD", "nodes": [], "edges": []}

    first = lines[0]
    if first.startswith("sequenceDiagram"):
        participants: Dict[str, str] = {}
        part_order: List[str] = []
        messages: List[Dict[str, Any]] = []

        def _ensure_part(pid: str, label: Optional[str] = None) -> None:
            p_clean = pid.strip()
            if not p_clean:
                return
            if p_clean not in participants:
                participants[p_clean] = _clean_mermaid_label(label) if label else p_clean
                part_order.append(p_clean)
            elif label:
                participants[p_clean] = _clean_mermaid_label(label)

        for s in lines[1:]:
            if re.match(r"^(autonumber|activate|deactivate|loop|alt|else|opt|par|rect|end|note\b)", s, re.IGNORECASE):
                continue
            m_p = re.match(r"^(?:participant|actor)\s+([^\s]+)(?:\s+as\s+(.+))?$", s, re.IGNORECASE)
            if m_p:
                _ensure_part(m_p.group(1), m_p.group(2))
                continue
            m_msg = re.match(r"^([^\s\-:]+)\s*(-->>|->>|-->|->|--x|-x|--\)|-\))\+?-?\s*([^\s\-:]+)\s*:\s*(.*)$", s)
            if m_msg:
                src, arrow, dst, msg = m_msg.group(1), m_msg.group(2), m_msg.group(3), m_msg.group(4)
                _ensure_part(src)
                _ensure_part(dst)
                messages.append({
                    "src": src,
                    "dst": dst,
                    "label": _clean_mermaid_label(msg),
                    "dashed": arrow.startswith("--"),
                })

        return {
            "kind": "sequence",
            "direction": "TD",
            "participants": [{"id": pid, "label": participants[pid]} for pid in part_order],
            "messages": messages,
        }

    direction = "TD"
    m_dir = re.match(r"^(?:flowchart|graph)\s+(TB|TD|BT|RL|LR)\b", first, re.IGNORECASE)
    if m_dir:
        d = m_dir.group(1).upper()
        direction = "LR" if d in ("LR", "RL") else "TD"
    elif first.startswith(("erDiagram", "classDiagram")):
        direction = "LR"

    nodes: Dict[str, Dict[str, str]] = {}
    node_order: List[str] = []
    edges: List[Dict[str, Any]] = []

    edge_split_re = re.compile(
        r"\s*(<\-\.\->|<\-\->|\-\.\->|\-\.[^\n]*?\.\->|==>|===|\-\-\->|\-\->|\-\-[^\n\-]*?\-\->|\-\-\s+[^\n\-]+?\s+\-\->|\-\-\||\|\-\->|\-\->\|[^|]*\||\|\-\.\->|\-\.\->\|[^|]*\||\|\|..\{|\|\|\-\-o\{|\|\|\-\-\|\||\}o\-\-\|\||<\|--|\*--|o--|\-\-\-)\s*"
    )

    body_lines = lines[1:] if re.match(r"^(flowchart|graph|stateDiagram|erDiagram|classDiagram)", first, re.IGNORECASE) else lines

    for s in body_lines:
        if s == "end" or s.startswith("{") or s == "}":
            continue
        m_sub = re.match(r"^subgraph\s+(?:([A-Za-z0-9_.\-]+)\s*\[\s*(.+?)\s*\]|(.+))$", s)
        if m_sub:
            continue
        m_state_as = re.match(r'^state\s+"([^"]+)"\s+as\s+([A-Za-z0-9_.\-]+)$', s)
        if m_state_as:
            lbl, nid = _clean_mermaid_label(m_state_as.group(1)), m_state_as.group(2)
            nodes[nid] = {"id": nid, "label": lbl, "shape": "round"}
            if nid not in node_order:
                node_order.append(nid)
            continue

        # 状態遷移やER図の `: ラベル` サフィックス対応
        trailing_label = ""
        s_work = s
        m_colon = re.match(r"^(.+?(?:-->|-\.->|\|\|--o\{|\|\|--\|\||\}o--\|\||<\|--|\*--|o--).+?)\s*:\s*(.+)$", s_work)
        if m_colon:
            s_work = m_colon.group(1).strip()
            trailing_label = _clean_mermaid_label(m_colon.group(2))

        # エッジ表現の正規化（`-->|label|` や `-- label -->` を共通トークン化）
        arrow_pat = re.compile(
            r"(\-\.\->\s*\|[^|]*\||"
            r"\-\->\s*\|[^|]*\||"
            r"==>\s*\|[^|]*\||"
            r"\-\.\s+[^.\n]+?\s+\.\->|"
            r"\-\-\s+[^-\n]+?\s+\-\->|"
            r"<\-\.\->|<\-\->|\-\.\->|==>|\-\-\->|\-\->|\-\-\-|"
            r"\|\|\-\-o\{|\|\|\-\-\|\||\}o\-\-\|\||<\|--|\*--|o--)"
        )
        parts = arrow_pat.split(s_work)
        if len(parts) >= 3:
            prev_id = _parse_mermaid_node_token(parts[0], nodes, node_order)
            idx = 1
            while idx + 1 < len(parts):
                raw_arrow = parts[idx].strip()
                target_tok = parts[idx + 1].strip()
                nxt_id = _parse_mermaid_node_token(target_tok, nodes, node_order)
                lbl = ""
                m_pipe = re.search(r"\|([^|]+)\|", raw_arrow)
                if m_pipe:
                    lbl = _clean_mermaid_label(m_pipe.group(1))
                else:
                    m_mid = re.match(r"^(?:\-\-|\-\.)\s+(.+?)\s+(?:\-\->|\.\->)$", raw_arrow)
                    if m_mid:
                        lbl = _clean_mermaid_label(m_mid.group(1))
                if not lbl and trailing_label and idx + 2 >= len(parts):
                    lbl = trailing_label
                dashed = ("-." in raw_arrow or ".->" in raw_arrow)
                directed = (">" in raw_arrow or "{" in raw_arrow or "<|" in raw_arrow)
                if prev_id and nxt_id:
                    edges.append({
                        "src": prev_id,
                        "dst": nxt_id,
                        "label": lbl,
                        "dashed": dashed,
                        "directed": directed,
                    })
                prev_id = nxt_id
                idx += 2
        else:
            _parse_mermaid_node_token(s_work, nodes, node_order)

    return {
        "kind": "flowchart",
        "direction": direction,
        "nodes": [nodes[nid] for nid in node_order],
        "edges": edges,
    }


def layout_mermaid_diagram(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    解析済みMermaid図を (0..1000, 0..1000) の正規化座標系にレイアウトする。
    戻り値には boxes (id, label, shape, x, y, w, h) と connectors (x1, y1, x2, y2, label, dashed, directed) を含む。
    """
    kind = parsed.get("kind", "empty")
    if kind == "sequence":
        parts = parsed.get("participants", [])
        msgs = parsed.get("messages", [])
        if not parts:
            return {"boxes": [], "connectors": [], "aspect": 0.45}

        p_cnt = len(parts)
        m_cnt = len(msgs)
        margin_x = 60.0
        usable_w = 1000.0 - 2 * margin_x
        box_w = min(180.0, max(90.0, usable_w / max(p_cnt, 1) * 0.72))
        box_h = 95.0
        top_y = 35.0

        boxes: List[Dict[str, Any]] = []
        lifeline_x: Dict[str, float] = {}
        for i, p in enumerate(parts):
            if p_cnt == 1:
                cx = 500.0
            else:
                cx = margin_x + box_w / 2 + i * ((usable_w - box_w) / (p_cnt - 1))
            bx = cx - box_w / 2
            lifeline_x[p["id"]] = cx
            boxes.append({
                "id": p["id"],
                "label": p["label"],
                "shape": "participant",
                "x": bx,
                "y": top_y,
                "w": box_w,
                "h": box_h,
            })

        connectors: List[Dict[str, Any]] = []
        start_msg_y = top_y + box_h + 65.0
        avail_msg_h = 940.0 - start_msg_y
        step_y = min(130.0, avail_msg_h / max(m_cnt, 1))
        bottom_y = start_msg_y + max(m_cnt - 1, 0) * step_y + 45.0

        # ライフライン（破線・矢印なし）
        for p in parts:
            cx = lifeline_x[p["id"]]
            connectors.append({
                "x1": cx, "y1": top_y + box_h,
                "x2": cx, "y2": bottom_y,
                "label": "", "dashed": True, "directed": False,
            })

        # メッセージ矢印
        for m_i, msg in enumerate(msgs):
            y = start_msg_y + m_i * step_y
            x1 = lifeline_x.get(msg["src"], 200.0)
            x2 = lifeline_x.get(msg["dst"], 800.0)
            if abs(x1 - x2) < 5.0:
                x2 = min(950.0, x1 + 110.0)
            connectors.append({
                "x1": x1, "y1": y,
                "x2": x2, "y2": y,
                "label": msg.get("label", ""),
                "dashed": bool(msg.get("dashed")),
                "directed": True,
            })

        aspect = min(0.85, max(0.38, 0.22 + 0.065 * m_cnt))
        return {"boxes": boxes, "connectors": connectors, "aspect": aspect}

    nodes = parsed.get("nodes", [])
    edges = parsed.get("edges", [])
    if not nodes:
        return {"boxes": [], "connectors": [], "aspect": 0.4}

    direction = parsed.get("direction", "TD")
    node_ids = [n["id"] for n in nodes]
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    in_deg: Dict[str, int] = {nid: 0 for nid in node_ids}

    for e in edges:
        u, v = e["src"], e["dst"]
        if u in adj and v in adj and u != v:
            # 後方エッジ（既に登場順が逆のループバック）はランク計算のDAGから除外して無限ループを防ぐ
            if id_to_idx[u] < id_to_idx[v] or in_deg[v] == 0:
                adj[u].append(v)
                in_deg[v] += 1

    ranks: Dict[str, int] = {nid: 0 for nid in node_ids}
    queue = [nid for nid in node_ids if in_deg[nid] == 0]
    if not queue:
        queue = [node_ids[0]]
    visited = set()
    while queue:
        curr = queue.pop(0)
        visited.add(curr)
        for nxt in adj.get(curr, []):
            if ranks[nxt] < ranks[curr] + 1:
                ranks[nxt] = min(ranks[curr] + 1, len(node_ids) - 1)
            in_deg[nxt] -= 1
            if in_deg[nxt] <= 0 and nxt not in visited:
                queue.append(nxt)

    # 1列に長すぎる場合（例: 8段以上の縦一列）は複数列へ折り返して視認性を高める
    max_rank = max(ranks.values()) if ranks else 0
    if max_rank >= 7 and len(nodes) >= 8:
        wrap_cols = 4 if direction == "LR" else 5
        for idx, nid in enumerate(node_ids):
            ranks[nid] = idx // wrap_cols

    layers: Dict[int, List[Dict[str, str]]] = {}
    for n in nodes:
        r = ranks.get(n["id"], 0)
        layers.setdefault(r, []).append(n)

    sorted_ranks = sorted(layers.keys())
    num_layers = len(sorted_ranks)
    max_in_layer = max(len(layers[r]) for r in sorted_ranks) if sorted_ranks else 1

    boxes = []
    box_map: Dict[str, Dict[str, Any]] = {}
    pad_x, pad_y = 45.0, 45.0
    usable_w = 1000.0 - 2 * pad_x
    usable_h = 1000.0 - 2 * pad_y

    if direction == "LR":
        col_step = usable_w / max(num_layers, 1)
        box_w = min(210.0, max(95.0, col_step * 0.68))
        for c_i, r_key in enumerate(sorted_ranks):
            layer_nodes = layers[r_key]
            m_cnt = len(layer_nodes)
            row_step = usable_h / max(m_cnt, 1)
            box_h = min(150.0, max(75.0, row_step * 0.66))
            cx = pad_x + (c_i + 0.5) * col_step
            for r_i, nd in enumerate(layer_nodes):
                cy = pad_y + (r_i + 0.5) * row_step
                b = {
                    "id": nd["id"],
                    "label": nd["label"],
                    "shape": nd["shape"],
                    "x": cx - box_w / 2,
                    "y": cy - box_h / 2,
                    "w": box_w,
                    "h": box_h,
                    "cx": cx,
                    "cy": cy,
                }
                boxes.append(b)
                box_map[nd["id"]] = b
        aspect = min(0.75, max(0.32, 0.18 * max_in_layer + 0.12))
    else:
        row_step = usable_h / max(num_layers, 1)
        box_h = min(135.0, max(65.0, row_step * 0.64))
        for r_i, r_key in enumerate(sorted_ranks):
            layer_nodes = layers[r_key]
            m_cnt = len(layer_nodes)
            col_step = usable_w / max(m_cnt, 1)
            box_w = min(240.0, max(105.0, col_step * 0.72))
            cy = pad_y + (r_i + 0.5) * row_step
            for c_i, nd in enumerate(layer_nodes):
                cx = pad_x + (c_i + 0.5) * col_step
                b = {
                    "id": nd["id"],
                    "label": nd["label"],
                    "shape": nd["shape"],
                    "x": cx - box_w / 2,
                    "y": cy - box_h / 2,
                    "w": box_w,
                    "h": box_h,
                    "cx": cx,
                    "cy": cy,
                }
                boxes.append(b)
                box_map[nd["id"]] = b
        aspect = min(0.85, max(0.36, 0.11 * num_layers + 0.12))

    def _border_point(b_from: Dict[str, Any], b_to: Dict[str, Any]) -> Tuple[float, float, float, float]:
        dx = b_to["cx"] - b_from["cx"]
        dy = b_to["cy"] - b_from["cy"]
        if abs(dx) > abs(dy) * 1.15:
            if dx >= 0:
                return (b_from["x"] + b_from["w"], b_from["cy"], b_to["x"], b_to["cy"])
            return (b_from["x"], b_from["cy"], b_to["x"] + b_to["w"], b_to["cy"])
        else:
            if dy >= 0:
                return (b_from["cx"], b_from["y"] + b_from["h"], b_to["cx"], b_to["y"])
            return (b_from["cx"], b_from["y"], b_to["cx"], b_to["y"] + b_to["h"])

    connectors = []
    for e in edges:
        b_u = box_map.get(e["src"])
        b_v = box_map.get(e["dst"])
        if not b_u or not b_v or b_u["id"] == b_v["id"]:
            continue
        x1, y1, x2, y2 = _border_point(b_u, b_v)
        connectors.append({
            "x1": x1, "y1": y1,
            "x2": x2, "y2": y2,
            "label": e.get("label", ""),
            "dashed": bool(e.get("dashed")),
            "directed": bool(e.get("directed", True)),
        })

    return {"boxes": boxes, "connectors": connectors, "aspect": aspect}


def _add_mermaid_diagram_docx(doc: Any, mermaid_code: str, diagram_idx: int = 1) -> bool:
    """
    Mermaid図をWord (.docx) 内で直接クリック・テキスト編集・移動が可能なネイティブVML図形グループ
    (<w:pict><v:group>) として段落に挿入する。
    """
    from xml.sax.saxutils import escape
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import parse_xml
    from docx.shared import Pt

    parsed = parse_mermaid_diagram(mermaid_code)
    layout = layout_mermaid_diagram(parsed)
    boxes = layout.get("boxes", [])
    connectors = layout.get("connectors", [])
    if not boxes:
        return False

    canvas_w_pt = 450.0
    canvas_h_pt = round(max(150.0, min(380.0, canvas_w_pt * float(layout.get("aspect", 0.48)))), 1)
    coord_w = 4500
    coord_h = int(round(canvas_h_pt * 10))

    vml_parts: List[str] = [
        f'<w:pict xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        f'xmlns:v="urn:schemas-microsoft-com:vml" '
        f'xmlns:o="urn:schemas-microsoft-com:office:office">',
        f'<v:group id="mermaid_grp_{diagram_idx}" '
        f'style="width:{canvas_w_pt}pt;height:{canvas_h_pt}pt;mso-position-horizontal:center" '
        f'coordsize="{coord_w},{coord_h}">',
        f'<v:rect id="mermaid_bg_{diagram_idx}" '
        f'style="position:absolute;left:0;top:0;width:{coord_w};height:{coord_h}" '
        f'fillcolor="#FAFCFF" strokecolor="#CBD5E0" strokeweight="0.75pt"/>',
    ]

    # 1. エッジ（矢印・コネクタ線）とエッジラベルを描画
    for c_i, conn in enumerate(connectors, start=1):
        x1 = int(round(conn["x1"] / 1000.0 * coord_w))
        y1 = int(round(conn["y1"] / 1000.0 * coord_h))
        x2 = int(round(conn["x2"] / 1000.0 * coord_w))
        y2 = int(round(conn["y2"] / 1000.0 * coord_h))
        dash_attr = ' dashstyle="dash"' if conn.get("dashed") else ""
        arrow_attr = ' endarrow="block"' if conn.get("directed", True) else ""
        stroke_col = "#6C757D" if (conn.get("dashed") and not conn.get("directed")) else "#2C5282"
        vml_parts.append(
            f'<v:line id="m_edge_{diagram_idx}_{c_i}" style="position:absolute" '
            f'from="{x1},{y1}" to="{x2},{y2}" strokecolor="{stroke_col}" strokeweight="1.2pt">'
            f'<v:stroke{dash_attr}{arrow_attr}/></v:line>'
        )
        lbl = conn.get("label", "").strip()
        if lbl:
            mx = int((x1 + x2) / 2)
            my = int((y1 + y2) / 2)
            lw = min(1400, max(520, len(lbl) * 110))
            lh = 220
            lx = max(20, min(coord_w - lw - 20, mx - lw // 2))
            ly = max(10, min(coord_h - lh - 10, my - lh - 10 if abs(y1 - y2) < 40 else my - lh // 2))
            vml_parts.append(
                f'<v:rect id="m_elbl_{diagram_idx}_{c_i}" '
                f'style="position:absolute;left:{lx};top:{ly};width:{lw};height:{lh}" '
                f'fillcolor="#FFFFFF" strokecolor="#CBD5E0" strokeweight="0.5pt">'
                f'<v:textbox inset="1pt,1pt,1pt,1pt"><w:txbxContent>'
                f'<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="0" w:after="0"/></w:pPr>'
                f'<w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="ＭＳ ゴシック"/>'
                f'<w:color w:val="2C5282"/><w:sz w:val="15"/></w:rPr>'
                f'<w:t>{escape(lbl)}</w:t></w:r></w:p>'
                f'</w:txbxContent></v:textbox></v:rect>'
            )

    # 2. ノード（編集可能なテキストボックス付きシェイプ）を描画
    for b_i, b in enumerate(boxes, start=1):
        bx = int(round(b["x"] / 1000.0 * coord_w))
        by = int(round(b["y"] / 1000.0 * coord_h))
        bw = max(360, int(round(b["w"] / 1000.0 * coord_w)))
        bh = max(220, int(round(b["h"] / 1000.0 * coord_h)))
        shp = b.get("shape", "rect")

        if shp == "participant":
            fill_hex, stroke_hex, txt_hex = "#1B365D", "#1B365D", "FFFFFF"
            tag = "v:roundrect"
            extra = ' arcsize="8000f"'
        elif shp == "diamond":
            fill_hex, stroke_hex, txt_hex = "#FFF4E5", "#D97706", "1B365D"
            tag = "v:roundrect"
            extra = ' arcsize="18000f"'
        elif shp == "cylinder":
            fill_hex, stroke_hex, txt_hex = "#E6F4EA", "#2E7D32", "1B365D"
            tag = "v:roundrect"
            extra = ' arcsize="12000f"'
        elif shp == "oval":
            fill_hex, stroke_hex, txt_hex = "#EBF3FA", "#2C5282", "1B365D"
            tag = "v:oval"
            extra = ""
        else:
            fill_hex, stroke_hex, txt_hex = "#EBF3FA", "#2C5282", "1B365D"
            tag = "v:roundrect"
            extra = ' arcsize="10000f"'

        p_xml_list: List[str] = []
        for ln_txt in str(b.get("label", "")).split("\n"):
            p_xml_list.append(
                f'<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="0" w:after="0"/></w:pPr>'
                f'<w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="ＭＳ ゴシック"/>'
                f'<w:b/><w:color w:val="{txt_hex}"/><w:sz w:val="17"/></w:rPr>'
                f'<w:t>{escape(ln_txt.strip())}</w:t></w:r></w:p>'
            )

        vml_parts.append(
            f'<{tag} id="m_node_{diagram_idx}_{b_i}" '
            f'style="position:absolute;left:{bx};top:{by};width:{bw};height:{bh}"{extra} '
            f'fillcolor="{fill_hex}" strokecolor="{stroke_hex}" strokeweight="1.2pt">'
            f'<v:textbox inset="2pt,2pt,2pt,2pt"><w:txbxContent>'
            f'{"".join(p_xml_list)}'
            f'</w:txbxContent></v:textbox></{tag}>'
        )

    vml_parts.append("</v:group></w:pict>")
    p = doc.add_paragraph(style="Normal")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run()
    r._r.append(parse_xml("".join(vml_parts)))
    return True



# ---------------------------------------------------------------------------
# Word (.docx / Normal.dotm) 入出力・差分パッチ
# ---------------------------------------------------------------------------

def _docx_style_has_numbering(doc: Any, style_name: str) -> bool:
    """指定されたWordスタイルに自動番号 (<w:numPr>) が定義されているか判定する。"""
    from docx.oxml.ns import qn

    if style_name not in doc.styles:
        return False
    st = doc.styles[style_name]
    pPr = st.element.find(qn("w:pPr"))
    if pPr is not None and pPr.find(qn("w:numPr")) is not None:
        return True
    return False


def _apply_docx_bullet_numpr(paragraph: Any, indent_level: int = 0, num_id: int = 2) -> None:
    """Normal.dotm の箇条書きリスト定義 (numId=2: ・ /  / ) を段落に適用する。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    pPr = paragraph._p.get_or_add_pPr()
    numPr = pPr.find(qn("w:numPr"))
    if numPr is None:
        numPr = OxmlElement("w:numPr")
        pPr.append(numPr)
    for child in list(numPr):
        numPr.remove(child)
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), str(min(max(indent_level, 0), 8)))
    numId = OxmlElement("w:numId")
    numId.set(qn("w:val"), str(num_id))
    numPr.append(ilvl)
    numPr.append(numId)


def _set_docx_run_font(run: Any, ascii_font: str = FONT_EN_WORD_BODY,
                       east_asia_font: str = FONT_JA_WORD_BODY,
                       size_pt: Optional[float] = None,
                       bold: Optional[bool] = None,
                       color_rgb: Optional[Tuple[int, int, int]] = None) -> None:
    """WordのRunに欧文フォントと日本語フォントを明示設定する。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    run.font.name = ascii_font
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), ascii_font)
    rFonts.set(qn("w:hAnsi"), ascii_font)
    rFonts.set(qn("w:eastAsia"), east_asia_font)

    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.font.bold = bold
    if color_rgb is not None:
        run.font.color.rgb = RGBColor(*color_rgb)


def _set_docx_cell_shading(cell: Any, hex_color: str) -> None:
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd"):
        tcPr.remove(old)
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)


def _set_docx_table_borders(table: Any, hex_color: str = "A0A0A0") -> None:
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    tblPr = table._tbl.tblPr
    for old in tblPr.findall("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblBorders"):
        tblPr.remove(old)
    borders_xml = f"""
    <w:tblBorders {nsdecls("w")}>
        <w:top w:val="single" w:sz="6" w:space="0" w:color="{hex_color}"/>
        <w:left w:val="single" w:sz="4" w:space="0" w:color="{hex_color}"/>
        <w:bottom w:val="single" w:sz="6" w:space="0" w:color="{hex_color}"/>
        <w:right w:val="single" w:sz="4" w:space="0" w:color="{hex_color}"/>
        <w:insideH w:val="single" w:sz="4" w:space="0" w:color="{hex_color}"/>
        <w:insideV w:val="single" w:sz="4" w:space="0" w:color="{hex_color}"/>
    </w:tblBorders>
    """
    tblPr.append(parse_xml(borders_xml))


def _append_rich_runs_docx(paragraph: Any, md_inline: str,
                           use_template_defaults: bool = True,
                           size_pt: Optional[float] = None) -> None:
    """
    段落内に `**太字**` や `` `コード` `` を解釈してRunを追加する。
    テンプレート（Normal.dotm）使用時は段落スタイルの既定フォント（Century/ＭＳ 明朝）を尊重する。
    """
    text = md_inline.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            r = paragraph.add_run(text[pos:m.start()])
            if not use_template_defaults or size_pt is not None:
                _set_docx_run_font(r, size_pt=size_pt)
        token = m.group(0)
        if token.startswith("**") and token.endswith("**"):
            r = paragraph.add_run(token[2:-2])
            r.bold = True
            if not use_template_defaults or size_pt is not None:
                _set_docx_run_font(r, bold=True, size_pt=size_pt)
        elif token.startswith("`") and token.endswith("`"):
            r = paragraph.add_run(token[1:-1])
            _set_docx_run_font(r, FONT_MONO, FONT_JA_WORD_HEAD, size_pt=size_pt or 9.5)
        pos = m.end()
    if pos < len(text):
        r = paragraph.add_run(text[pos:])
        if not use_template_defaults or size_pt is not None:
            _set_docx_run_font(r, size_pt=size_pt)


def open_word_document(tpl_path: Optional[Path] = None) -> Any:
    """テンプレート（.dotm/.dotx/.docx）または新規Wordドキュメントを開く。"""
    import docx

    resolved = resolve_word_template(tpl_path)
    if resolved is not None:
        ext = resolved.suffix.lower()
        if ext in (".dotm", ".dotx"):
            stream = _load_template_as_document_stream(resolved, is_word=True)
            return docx.Document(stream)
        return docx.Document(str(resolved))
    return docx.Document()


def export_md_to_docx(md_path: Path, out_path: Path,
                      template_path: Optional[Path] = None,
                      title_override: Optional[str] = None) -> None:
    """
    Markdown文書を Word (.docx) に変換する。
    Normal.dotm 等のテンプレートの余白・ヘッダ/フッタ・見出し自動採番・インデントスタイルを完全保持する。
    """
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    doc = open_word_document(template_path)

    # テンプレート内の初期空段落をクリア（セクション設定・ヘッダ・フッタ・スタイルは完全維持）
    for p in list(doc.paragraphs):
        p._element.getparent().remove(p._element)
    for t in list(doc.tables):
        t._element.getparent().remove(t._element)

    md_text = md_path.read_text(encoding="utf-8-sig")
    meta, blocks = parse_markdown(md_text)

    # 文書タイトルの決定（frontmatter title または最初の # 見出し）
    doc_title = title_override or meta.get("title")
    first_h1_consumed = False
    if not doc_title:
        for b in blocks:
            if b.kind == "heading" and b.level == 1:
                doc_title = clean_inline_md(b.text)
                first_h1_consumed = True
                break

    if doc_title:
        p = doc.add_paragraph(style="Title" if "Title" in doc.styles else "Normal")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(14)
        r = p.add_run(doc_title)
        _set_docx_run_font(r, FONT_EN_WORD_HEAD, FONT_JA_WORD_HEAD, size_pt=16.0, bold=True)

    # Normal.dotm は見出し直後の本文に 'Normal Indent' (styleId='a0') を用いる設計
    body_style = "Normal Indent" if "Normal Indent" in doc.styles else "Normal"
    has_h1_num = _docx_style_has_numbering(doc, "Heading 1")
    mermaid_idx = 0

    for blk in blocks:
        if blk.kind == "heading":
            if blk.level == 1:
                if first_h1_consumed or (doc_title and clean_inline_md(blk.text) == doc_title):
                    first_h1_consumed = False
                    doc_title = None
                    continue
                w_level = 1
            else:
                # Markdownの ## (章) -> Wordの Heading 1、### (節) -> Heading 2、#### (項) -> Heading 3
                w_level = min(blk.level - 1, 9)

            st_name = f"Heading {w_level}" if f"Heading {w_level}" in doc.styles else "Normal"
            p = doc.add_paragraph(style=st_name)
            h_text = strip_heading_number(blk.text) if _docx_style_has_numbering(doc, st_name) else clean_inline_md(blk.text)
            p.add_run(h_text)

        elif blk.kind == "paragraph":
            p = doc.add_paragraph(style=body_style)
            _append_rich_runs_docx(p, blk.text, use_template_defaults=True)

        elif blk.kind == "note":
            p = doc.add_paragraph(style=body_style)
            _append_rich_runs_docx(p, blk.text, use_template_defaults=True)

        elif blk.kind == "list":
            for indent, item_text, is_ordered in blk.items:
                if not is_ordered and has_h1_num:
                    # Normal.dotm の箇条書き定義 (numId=2: ・ /  / ) を使用
                    p = doc.add_paragraph(style="Normal")
                    _apply_docx_bullet_numpr(p, indent_level=indent, num_id=2)
                    _append_rich_runs_docx(p, item_text, use_template_defaults=True)
                else:
                    st_name = "List Number" if is_ordered else "List Bullet"
                    p = doc.add_paragraph(style=st_name if st_name in doc.styles else body_style)
                    if indent > 0:
                        p.paragraph_format.left_indent = Pt(18 * (indent + 1))
                    prefix = "" if st_name in doc.styles else ("・" if not is_ordered else "1. ")
                    _append_rich_runs_docx(p, prefix + item_text, use_template_defaults=True)

        elif blk.kind == "code":
            lang = blk.meta.get("lang", "").strip().lower()
            if lang == "mermaid":
                mermaid_idx += 1
                if _add_mermaid_diagram_docx(doc, blk.text, diagram_idx=mermaid_idx):
                    continue
            p = doc.add_paragraph(style="Normal")
            p.paragraph_format.left_indent = Pt(14)
            p.paragraph_format.right_indent = Pt(14)
            r = p.add_run(blk.text)
            _set_docx_run_font(r, FONT_MONO, FONT_JA_WORD_HEAD, size_pt=9.0, bold=False)

        elif blk.kind == "table" and blk.rows:
            num_rows = len(blk.rows)
            num_cols = max(len(r) for r in blk.rows)
            table = doc.add_table(rows=num_rows, cols=num_cols)
            table.autofit = True
            _set_docx_table_borders(table)

            for r_idx, row_data in enumerate(blk.rows):
                row_cells = table.rows[r_idx].cells
                is_header = (r_idx == 0)
                bg_hex = "D9E1F2" if is_header else "FFFFFF"
                for c_idx in range(num_cols):
                    val = row_data[c_idx] if c_idx < len(row_data) else ""
                    cell = row_cells[c_idx]
                    _set_docx_cell_shading(cell, bg_hex)
                    cp = cell.paragraphs[0]
                    cp.paragraph_format.space_before = Pt(2)
                    cp.paragraph_format.space_after = Pt(2)
                    if is_header:
                        run = cp.add_run(clean_inline_md(val))
                        _set_docx_run_font(run, FONT_EN_WORD_HEAD, FONT_JA_WORD_HEAD, size_pt=9.5, bold=True)
                    else:
                        _append_rich_runs_docx(cp, val, use_template_defaults=False, size_pt=9.5)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))


def import_docx_to_md(docx_path: Path) -> str:
    """既存の Word (.docx / .dotm) 文書を見出し階層・段落・表の順序を保って Markdown に変換する。"""
    doc = open_word_document(docx_path)
    lines: List[str] = [f"<!-- source_office: {docx_path.as_posix()} -->", ""]

    para_map = {p._element: p for p in doc.paragraphs}
    tbl_map = {t._element: t for t in doc.tables}
    has_title = False

    for child in doc.element.body.iterchildren():
        if child in para_map:
            p = para_map[child]
            text = p.text.strip()
            if not text:
                continue
            style_name = (p.style.name if p.style else "Normal") or "Normal"
            style_low = style_name.lower()
            if style_low == "title" or (not has_title and p.alignment == 1 and len(lines) <= 3):
                lines.append(f"# {text}")
                lines.append("")
                has_title = True
            elif style_low.startswith("heading"):
                m = re.search(r"(\d+)", style_low)
                lvl = int(m.group(1)) if m else 1
                # Titleがある文書では Wordの Heading 1 -> Markdownの ## にマップ
                md_lvl = min(lvl + (1 if has_title else 0), 6)
                lines.append(f"{'#' * md_lvl} {text}")
                lines.append("")
            elif "bullet" in style_low or (p._p.pPr is not None and p._p.pPr.numPr is not None):
                lines.append(f"- {text}")
            elif "number" in style_low:
                lines.append(f"1. {text}")
            else:
                lines.append(text)
                lines.append("")

        elif child in tbl_map:
            t = tbl_map[child]
            if not t.rows:
                continue
            md_rows: List[List[str]] = []
            for row in t.rows:
                cells = [c.text.strip().replace("\n", "<br>") for c in row.cells]
                md_rows.append(cells)
            if md_rows:
                col_count = max(len(r) for r in md_rows)
                header = md_rows[0] + [""] * (col_count - len(md_rows[0]))
                lines.append("| " + " | ".join(header) + " |")
                lines.append("| " + " | ".join(["---"] * col_count) + " |")
                for r in md_rows[1:]:
                    padded = r + [""] * (col_count - len(r))
                    lines.append("| " + " | ".join(padded) + " |")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _replace_docx_paragraph_text_preserve_style(paragraph: Any, new_text: str) -> None:
    """段落の既存スタイルと先頭Runの書式(<w:rPr>)を保持したままテキストのみを差し替える。"""
    clean_text = clean_inline_md(new_text)
    if not paragraph.runs:
        paragraph.add_run(clean_text)
        return
    first_run = paragraph.runs[0]
    first_run.text = clean_text
    for extra_run in paragraph.runs[1:]:
        extra_run._r.getparent().remove(extra_run._r)


def patch_docx_with_md(base_docx: Path, md_path: Path, out_docx: Path) -> Dict[str, int]:
    """既存の Word (.docx) 資産の書式・スタイルを崩さずに、Markdownの変更を差分反映する。"""
    doc = open_word_document(base_docx)
    _, blocks = parse_markdown(md_path.read_text(encoding="utf-8-sig"))

    stats = {"updated_tables": 0, "updated_rows": 0, "added_rows": 0,
             "updated_paragraphs": 0, "added_blocks": 0}

    md_tables = [b.rows for b in blocks if b.kind == "table" and len(b.rows) >= 1]

    for tbl_idx, md_rows in enumerate(md_tables):
        if tbl_idx >= len(doc.tables):
            break
        doc_tbl = doc.tables[tbl_idx]
        if not doc_tbl.rows:
            continue
        stats["updated_tables"] += 1

        existing_key_map: Dict[str, Any] = {}
        for d_row in doc_tbl.rows[1:]:
            key = d_row.cells[0].text.strip()
            if key:
                existing_key_map[key] = d_row

        template_tr = copy.deepcopy(doc_tbl.rows[-1]._tr) if len(doc_tbl.rows) > 1 else None

        for m_i, m_row in enumerate(md_rows[1:], start=1):
            row_key = clean_inline_md(m_row[0]) if m_row else ""
            target_row = existing_key_map.get(row_key)
            if target_row is None and m_i < len(doc_tbl.rows) and not row_key.startswith(("REQ-", "TC-", "UNIT-", "B", "EV-")):
                target_row = doc_tbl.rows[m_i]

            if target_row is not None:
                changed = False
                for c_i, val in enumerate(m_row):
                    if c_i < len(target_row.cells):
                        new_val = clean_inline_md(val)
                        if target_row.cells[c_i].text.strip() != new_val:
                            _replace_docx_paragraph_text_preserve_style(
                                target_row.cells[c_i].paragraphs[0], new_val
                            )
                            changed = True
                if changed:
                    stats["updated_rows"] += 1
            else:
                if template_tr is not None:
                    new_tr = copy.deepcopy(template_tr)
                    doc_tbl._tbl.append(new_tr)
                    new_row = doc_tbl.rows[-1]
                else:
                    new_row = doc_tbl.add_row()
                for c_i, val in enumerate(m_row):
                    if c_i < len(new_row.cells):
                        _replace_docx_paragraph_text_preserve_style(
                            new_row.cells[c_i].paragraphs[0], clean_inline_md(val)
                        )
                stats["added_rows"] += 1

    heading_to_paras: Dict[str, List[Any]] = {}
    current_head = "__ROOT__"
    heading_to_paras[current_head] = []
    for p_idx, p in enumerate(doc.paragraphs):
        st_name = (p.style.name if p.style else "Normal").lower()
        # 先頭の中央揃え段落（文書タイトル）も見出しキーとして登録する
        is_top_title = (p_idx == 0 and p.alignment == 1 and p.text.strip())
        if st_name == "title" or st_name.startswith("heading") or is_top_title:
            current_head = strip_heading_number(p.text.strip())
            heading_to_paras.setdefault(current_head, [])
        else:
            heading_to_paras.setdefault(current_head, []).append(p)

    md_head = "__ROOT__"
    md_head_paras: Dict[str, List[Tuple[int, str]]] = {md_head: []}
    for b in blocks:
        if b.kind == "heading":
            md_head = strip_heading_number(b.text)
            md_head_paras.setdefault(md_head, [])
        elif b.kind == "paragraph":
            md_head_paras.setdefault(md_head, []).append((0, b.text))
        elif b.kind == "list":
            for _, item_txt, _ in b.items:
                md_head_paras.setdefault(md_head, []).append((1, item_txt))

    body_style = "Normal Indent" if "Normal Indent" in doc.styles else "Normal"
    for h_text, p_list in md_head_paras.items():
        if h_text in heading_to_paras:
            doc_paras = heading_to_paras[h_text]
            for idx, (_, new_p_text) in enumerate(p_list):
                cleaned = clean_inline_md(new_p_text)
                if idx < len(doc_paras):
                    if doc_paras[idx].text.strip() != cleaned:
                        _replace_docx_paragraph_text_preserve_style(doc_paras[idx], cleaned)
                        stats["updated_paragraphs"] += 1
        elif h_text != "__ROOT__":
            st_h = "Heading 1" if "Heading 1" in doc.styles else "Normal"
            hp = doc.add_paragraph(style=st_h)
            hp.add_run(h_text)
            stats["added_blocks"] += 1
            for is_list, new_p_text in p_list:
                np = doc.add_paragraph(style="Normal" if is_list else body_style)
                if is_list:
                    _apply_docx_bullet_numpr(np, indent_level=0, num_id=2)
                _append_rich_runs_docx(np, new_p_text, use_template_defaults=True)
                stats["added_blocks"] += 1

    out_docx.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_docx))
    return stats


# ---------------------------------------------------------------------------
# PowerPoint (.pptx / Blank.potx) 入出力・差分パッチ
# ---------------------------------------------------------------------------

def open_ppt_presentation(tpl_path: Optional[Path] = None) -> Any:
    """テンプレート（.potx/.potm/.pptx）または新規PowerPointプレゼンテーションを開く。"""
    from pptx import Presentation

    resolved = resolve_ppt_template(tpl_path)
    if resolved is not None:
        ext = resolved.suffix.lower()
        if ext in (".potx", ".potm"):
            stream = _load_template_as_document_stream(resolved, is_word=False)
            return Presentation(stream)
        return Presentation(str(resolved))
    return Presentation()


def _delete_all_slides(prs: Any) -> None:
    """テンプレートに含まれる初期サンプルスライドをクリアする（スライドマスターとレイアウトは完全維持）。"""
    xml_slides = prs.slides._sldIdLst
    slides = list(xml_slides)
    for s in slides:
        rId = s.rId
        prs.part.drop_rel(rId)
        xml_slides.remove(s)


def _find_slide_layout(prs: Any, preferred_names: Tuple[str, ...], fallback_idx: int) -> Any:
    """レイアウト名またはインデックスから最適なスライドレイアウトを取得する。"""
    for ly in prs.slide_layouts:
        if ly.name in preferred_names:
            return ly
    if 0 <= fallback_idx < len(prs.slide_layouts):
        return prs.slide_layouts[fallback_idx]
    return prs.slide_layouts[0]


def _get_slide_placeholder(slide: Any, idx: int) -> Optional[Any]:
    """
    python-pptx の SlidePlaceholders は `idx in slide.placeholders` が常に False になる仕様のため、
    placeholder_format.idx を明示走査して該当プレースホルダを取得する。
    """
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == idx:
            return ph
    if idx == 1:
        for ph in slide.placeholders:
            if ph != slide.shapes.title and ph.has_text_frame and ph.placeholder_format.type not in (13, 15, 16):
                return ph
    return None


def _add_mermaid_diagram_pptx(slide: Any, mermaid_code: str,
                              left_in: float = 0.85, top_in: float = 2.8,
                              width_in: float = 11.6, height_in: float = 3.55) -> bool:
    """
    Mermaid図を PowerPoint スライド上に直接クリック・編集可能なネイティブシェイプと矢印コネクタとして描画する。
    """
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls
    from pptx.util import Inches, Pt

    parsed = parse_mermaid_diagram(mermaid_code)
    layout = layout_mermaid_diagram(parsed)
    boxes = layout.get("boxes", [])
    connectors = layout.get("connectors", [])
    if not boxes:
        return False

    # 1. エッジ（矢印付きコネクタ・破線）とラベルを描画
    for conn in connectors:
        x1 = Inches(left_in + (conn["x1"] / 1000.0) * width_in)
        y1 = Inches(top_in + (conn["y1"] / 1000.0) * height_in)
        x2 = Inches(left_in + (conn["x2"] / 1000.0) * width_in)
        y2 = Inches(top_in + (conn["y2"] / 1000.0) * height_in)
        c_shp = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
        c_shp.line.width = Pt(1.5)
        is_lifeline = bool(conn.get("dashed") and not conn.get("directed", True))
        c_shp.line.color.rgb = RGBColor(*(COLOR_MUTED if is_lifeline else COLOR_SECONDARY))

        ln_el = c_shp.line._get_or_add_ln()
        if conn.get("dashed"):
            for old_d in ln_el.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}prstDash"):
                ln_el.remove(old_d)
            ln_el.append(parse_xml(f'<a:prstDash {nsdecls("a")} val="dash"/>'))
        if conn.get("directed", True):
            for old_t in ln_el.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd"):
                ln_el.remove(old_t)
            ln_el.append(parse_xml(f'<a:tailEnd {nsdecls("a")} type="triangle" w="med" len="med"/>'))

        lbl = conn.get("label", "").strip()
        if lbl:
            mx_in = left_in + ((conn["x1"] + conn["x2"]) / 2000.0) * width_in
            my_in = top_in + ((conn["y1"] + conn["y2"]) / 2000.0) * height_in
            lw_in = min(2.6, max(0.95, len(lbl) * 0.14 + 0.3))
            lh_in = 0.28
            tb = slide.shapes.add_textbox(
                Inches(mx_in - lw_in / 2),
                Inches(my_in - lh_in - 0.03 if abs(conn["y1"] - conn["y2"]) < 25 else my_in - lh_in / 2),
                Inches(lw_in),
                Inches(lh_in),
            )
            tb.fill.solid()
            tb.fill.fore_color.rgb = RGBColor(255, 255, 255)
            tf = tb.text_frame
            tf.word_wrap = True
            tf.margin_left = Pt(2)
            tf.margin_right = Pt(2)
            tf.margin_top = Pt(1)
            tf.margin_bottom = Pt(1)
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run()
            r.text = lbl
            r.font.name = FONT_JA_PRESENTATION
            r.font.size = Pt(9.5)
            r.font.color.rgb = RGBColor(*COLOR_SECONDARY)

    # 2. ノード（編集可能なPowerPoint図形）を描画
    for b in boxes:
        bx = Inches(left_in + (b["x"] / 1000.0) * width_in)
        by = Inches(top_in + (b["y"] / 1000.0) * height_in)
        bw = Inches(max(0.85, (b["w"] / 1000.0) * width_in))
        bh = Inches(max(0.38, (b["h"] / 1000.0) * height_in))
        shp_kind = b.get("shape", "rect")

        if shp_kind == "diamond":
            mso_type = MSO_SHAPE.DIAMOND
            fill_rgb, border_rgb, txt_rgb = (255, 244, 229), (217, 119, 6), COLOR_PRIMARY
        elif shp_kind == "cylinder":
            mso_type = MSO_SHAPE.ROUNDED_RECTANGLE
            fill_rgb, border_rgb, txt_rgb = (230, 244, 234), (46, 125, 50), COLOR_PRIMARY
        elif shp_kind == "oval":
            mso_type = MSO_SHAPE.OVAL
            fill_rgb, border_rgb, txt_rgb = (235, 243, 250), COLOR_SECONDARY, COLOR_PRIMARY
        elif shp_kind == "participant":
            mso_type = MSO_SHAPE.ROUNDED_RECTANGLE
            fill_rgb, border_rgb, txt_rgb = COLOR_PRIMARY, COLOR_PRIMARY, (255, 255, 255)
        else:
            mso_type = MSO_SHAPE.ROUNDED_RECTANGLE
            fill_rgb, border_rgb, txt_rgb = (235, 243, 250), COLOR_SECONDARY, COLOR_PRIMARY

        node_shp = slide.shapes.add_shape(mso_type, bx, by, bw, bh)
        node_shp.fill.solid()
        node_shp.fill.fore_color.rgb = RGBColor(*fill_rgb)
        node_shp.line.color.rgb = RGBColor(*border_rgb)
        node_shp.line.width = Pt(1.5)

        tf = node_shp.text_frame
        tf.clear()
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = Pt(4)
        tf.margin_right = Pt(4)
        tf.margin_top = Pt(2)
        tf.margin_bottom = Pt(2)

        for l_i, ln_txt in enumerate(str(b.get("label", "")).split("\n")):
            p = tf.paragraphs[0] if l_i == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run()
            r.text = ln_txt.strip()
            r.font.name = FONT_JA_PRESENTATION
            r.font.size = Pt(10.5)
            r.font.bold = True
            r.font.color.rgb = RGBColor(*txt_rgb)

    return True


def _group_blocks_into_slides(meta: Dict[str, str], blocks: List[MdBlock],
                              fallback_title: str) -> Tuple[str, str, List[Dict[str, Any]]]:
    """Markdownブロック列を表紙情報と各スライドデータに構造化する。"""
    deck_title = meta.get("title", "")
    deck_subtitle = meta.get("subtitle", meta.get("description", ""))
    slides: List[Dict[str, Any]] = []
    current_slide: Optional[Dict[str, Any]] = None

    def _has_slide_content(s: Optional[Dict[str, Any]]) -> bool:
        if not s:
            return False
        return bool(s["bullets"] or s["tables"] or s["code"] or s["mermaid"])

    for blk in blocks:
        if blk.kind == "heading" and blk.level == 1 and current_slide is None and not slides:
            if not deck_title:
                deck_title = clean_inline_md(blk.text)
            continue

        if blk.kind == "rule":
            if _has_slide_content(current_slide):
                slides.append(current_slide)  # type: ignore[arg-type]
                current_slide = None
            continue

        if blk.kind == "heading" and blk.level in (1, 2):
            if _has_slide_content(current_slide):
                slides.append(current_slide)  # type: ignore[arg-type]
            current_slide = {
                "title": clean_inline_md(blk.text),
                "bullets": [],
                "tables": [],
                "code": [],
                "mermaid": [],
                "notes": [],
            }
            continue

        if current_slide is None:
            if blk.kind == "paragraph" and not deck_subtitle and not slides:
                deck_subtitle = clean_inline_md(blk.text)
                continue
            current_slide = {
                "title": "概要",
                "bullets": [],
                "tables": [],
                "code": [],
                "mermaid": [],
                "notes": [],
            }

        if blk.kind == "heading" and blk.level >= 3:
            current_slide["bullets"].append((0, clean_inline_md(blk.text)))
        elif blk.kind == "paragraph":
            current_slide["bullets"].append((0, clean_inline_md(blk.text)))
        elif blk.kind == "list":
            for indent, itm, _ in blk.items:
                current_slide["bullets"].append((min(indent, 4), clean_inline_md(itm)))
        elif blk.kind == "table" and blk.rows:
            current_slide["tables"].append(blk.rows)
        elif blk.kind == "code":
            if blk.meta.get("lang", "").strip().lower() == "mermaid":
                current_slide["mermaid"].append(blk.text)
            else:
                current_slide["code"].append(blk.text)
        elif blk.kind == "note":
            current_slide["notes"].append(clean_inline_md(blk.text))

    if _has_slide_content(current_slide):
        slides.append(current_slide)  # type: ignore[arg-type]

    if not deck_title:
        deck_title = fallback_title
    return deck_title, deck_subtitle, slides


def export_md_to_pptx(md_path: Path, out_path: Path,
                      template_path: Optional[Path] = None,
                      title_override: Optional[str] = None) -> None:
    """
    Markdown文書から PowerPoint (.pptx) を生成する。
    Blank.potx のスライドマスター（ヘッダ/フッタ線、Arial+メイリオ、プレースホルダ、スライド番号）をそのまま活用する。
    """
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = open_ppt_presentation(template_path)
    _delete_all_slides(prs)

    md_text = md_path.read_text(encoding="utf-8-sig")
    meta, blocks = parse_markdown(md_text)
    deck_title, deck_subtitle, slides_data = _group_blocks_into_slides(
        meta, blocks, title_override or md_path.stem
    )
    if title_override:
        deck_title = title_override

    title_layout = _find_slide_layout(prs, ("タイトル スライド", "Title Slide"), 0)
    content_layout = _find_slide_layout(prs, ("タイトルとコンテンツ", "Title and Content"), 1)
    title_only_layout = _find_slide_layout(prs, ("タイトルのみ", "Title Only"), 5)

    # 1. 表紙スライド（Blank.potx の「タイトル スライド」レイアウトを使用）
    cover = prs.slides.add_slide(title_layout)
    if cover.shapes.title:
        cover.shapes.title.text = deck_title
    sub_ph = _get_slide_placeholder(cover, 1)
    if sub_ph is not None:
        sub_ph.text = deck_subtitle or ""

    # 2. コンテンツスライド（Blank.potx の「タイトルとコンテンツ」または「タイトルのみ」を使用）
    for sdata in slides_data:
        has_bullets = bool(sdata["bullets"])
        has_table = bool(sdata["tables"])
        has_mermaid = bool(sdata.get("mermaid"))
        has_code = bool(sdata.get("code"))
        layout = content_layout if has_bullets else title_only_layout
        slide = prs.slides.add_slide(layout)

        if slide.shapes.title:
            slide.shapes.title.text = sdata["title"]

        # 箇条書きの流し込み（Blank.potx のコンテンツプレースホルダ idx=1 を使用）
        if has_bullets:
            body_ph = _get_slide_placeholder(slide, 1)
            if body_ph is None:
                body_ph = slide.shapes.add_textbox(Inches(0.8), Inches(1.0), Inches(11.7), Inches(5.2))
            if has_table or has_mermaid or has_code:
                # 下部に表や図を配置するためテキスト枠の高さを調整
                body_ph.top = Inches(0.95)
                body_ph.height = Inches(1.85 if (has_table or has_mermaid) else 2.2)
            tf = body_ph.text_frame
            tf.clear()
            tf.word_wrap = True
            for b_i, (indent_lvl, b_text) in enumerate(sdata["bullets"][:12]):
                p = tf.paragraphs[0] if b_i == 0 else tf.add_paragraph()
                p.text = b_text
                p.level = min(max(indent_lvl, 0), 4)
                for r in p.runs:
                    r.font.name = FONT_JA_PRESENTATION
                    r.font.size = Pt(16 if indent_lvl == 0 else 14)
                    r.font.color.rgb = RGBColor(0, 0, 0)

        # Mermaid図のネイティブ編集可能シェイプ配置
        if has_mermaid:
            diag_top = 2.85 if has_bullets else 1.15
            diag_h = 3.55 if has_bullets else 5.25
            if has_table:
                diag_h = 2.0
            _add_mermaid_diagram_pptx(
                slide, sdata["mermaid"][0],
                left_in=0.85, top_in=diag_top, width_in=11.6, height_in=diag_h
            )

        # 表の配置（Blank.potx のフッタ線 y=6.55inch の内側に収める）
        if has_table:
            t_rows = sdata["tables"][0][:MAX_SLIDE_TABLE_ROWS]
            r_cnt = len(t_rows)
            c_cnt = max(len(r) for r in t_rows)
            if has_mermaid:
                tbl_top = Inches(4.95)
                max_tbl_h = 1.5
            else:
                tbl_top = Inches(3.0) if has_bullets else Inches(1.15)
                max_tbl_h = 5.4 if not has_bullets else 3.45
            tbl_h = min(max_tbl_h, 0.38 * r_cnt)

            graphic_frame = slide.shapes.add_table(
                r_cnt, c_cnt, Inches(0.8), tbl_top, Inches(11.7), Inches(tbl_h)
            )
            tbl = graphic_frame.table
            for r_i, r_data in enumerate(t_rows):
                for c_i in range(c_cnt):
                    val = clean_inline_md(r_data[c_i]) if c_i < len(r_data) else ""
                    cell = tbl.cell(r_i, c_i)
                    cell.text = val
                    cell.fill.solid()
                    if r_i == 0:
                        cell.fill.fore_color.rgb = RGBColor(217, 225, 242)
                    else:
                        cell.fill.fore_color.rgb = RGBColor(*(COLOR_BG_LIGHT if r_i % 2 == 1 else (255, 255, 255)))
                    for cp in cell.text_frame.paragraphs:
                        cp.font.name = FONT_JA_PRESENTATION
                        cp.font.size = Pt(12 if r_i == 0 else 11)
                        cp.font.bold = (r_i == 0)
                        cp.font.color.rgb = RGBColor(0, 0, 0)

        elif has_code and not has_mermaid:
            code_top = Inches(3.2) if has_bullets else Inches(1.2)
            code_h = Inches(3.1) if has_bullets else Inches(5.1)
            cb = slide.shapes.add_textbox(Inches(0.8), code_top, Inches(11.7), code_h)
            cb.fill.solid()
            cb.fill.fore_color.rgb = RGBColor(*COLOR_BG_LIGHT)
            ctf = cb.text_frame
            ctf.word_wrap = True
            cp = ctf.paragraphs[0]
            cp.text = sdata["code"][0][:800]
            for r in cp.runs:
                r.font.name = FONT_MONO
                r.font.size = Pt(10.5)
                r.font.color.rgb = RGBColor(0, 0, 0)

        if sdata["notes"]:
            notes_slide = slide.notes_slide
            notes_slide.notes_text_frame.text = "\n".join(sdata["notes"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))


def import_pptx_to_md(pptx_path: Path) -> str:
    """既存の PowerPoint (.pptx / .potx) の全スライド・表・ノートを構造化 Markdown に変換する。"""
    prs = open_ppt_presentation(pptx_path)
    lines: List[str] = [f"<!-- source_office: {pptx_path.as_posix()} -->", ""]

    for s_idx, slide in enumerate(prs.slides, start=1):
        title_text = ""
        if slide.shapes.title and slide.shapes.title.text.strip():
            title_text = slide.shapes.title.text.strip().replace("\n", " ")

        text_shapes = []
        tables = []
        for shp in slide.shapes:
            if shp.has_table:
                tables.append(shp.table)
            elif shp.has_text_frame:
                if shp.is_placeholder and shp.placeholder_format.type in (13, 15, 16):
                    # SLIDE_NUMBER(13), FOOTER(15), DATE(16) は除外
                    continue
                txt = shp.text_frame.text.strip()
                if not txt or re.match(r"^\d+\s*/\s*\d+$", txt):
                    continue
                text_shapes.append((shp.top or 0, shp.left or 0, shp))

        text_shapes.sort(key=lambda x: (x[0], x[1]))
        if not title_text and text_shapes:
            first_shp = text_shapes[0][2]
            title_text = first_shp.text_frame.paragraphs[0].text.strip()
            text_shapes = text_shapes[1:]

        if s_idx == 1 and title_text:
            lines.append(f"# {title_text}")
            lines.append("")
        else:
            lines.append(f"## {title_text or f'スライド {s_idx}'}")
            lines.append("")

        for _, _, shp in text_shapes:
            if slide.shapes.title and shp == slide.shapes.title:
                continue
            for p in shp.text_frame.paragraphs:
                ptxt = p.text.strip()
                if not ptxt:
                    continue
                ptxt_clean = re.sub(r"^[•▸▪\-*]\s*", "", ptxt)
                if s_idx == 1 and len(lines) <= 3:
                    lines.append(ptxt_clean)
                    lines.append("")
                else:
                    indent = "  " * (p.level or 0)
                    lines.append(f"{indent}- {ptxt_clean}")
        if text_shapes:
            lines.append("")

        for tbl in tables:
            md_rows: List[List[str]] = []
            for r in tbl.rows:
                md_rows.append([c.text.strip().replace("\n", "<br>") for c in r.cells])
            if md_rows:
                c_cnt = max(len(r) for r in md_rows)
                hdr = md_rows[0] + [""] * (c_cnt - len(md_rows[0]))
                lines.append("| " + " | ".join(hdr) + " |")
                lines.append("| " + " | ".join(["---"] * c_cnt) + " |")
                for r in md_rows[1:]:
                    padded = r + [""] * (c_cnt - len(r))
                    lines.append("| " + " | ".join(padded) + " |")
                lines.append("")

        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            note_txt = slide.notes_slide.notes_text_frame.text.strip()
            if note_txt:
                for nline in note_txt.split("\n"):
                    if nline.strip():
                        lines.append(f"> {nline.strip()}")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _replace_pptx_paragraph_preserve_font(paragraph: Any, new_text: str) -> None:
    if paragraph.runs:
        first_run = paragraph.runs[0]
        first_run.text = new_text
        for extra in paragraph.runs[1:]:
            extra._r.getparent().remove(extra._r)
    else:
        paragraph.text = new_text


def patch_pptx_with_md(base_pptx: Path, md_path: Path, out_pptx: Path) -> Dict[str, int]:
    """既存の PowerPoint (.pptx) のレイアウト・プレースホルダ・フォント属性を崩さずに差分反映する。"""
    prs = open_ppt_presentation(base_pptx)
    meta, blocks = parse_markdown(md_path.read_text(encoding="utf-8-sig"))
    deck_title, deck_sub, md_slides = _group_blocks_into_slides(meta, blocks, md_path.stem)

    stats = {"updated_slides": 0, "updated_shapes": 0, "added_slides": 0}
    slide_list = list(prs.slides)

    # 表紙の更新
    if slide_list and deck_title:
        cover = slide_list[0]
        if cover.shapes.title and cover.shapes.title.text.strip() != deck_title:
            _replace_pptx_paragraph_preserve_font(cover.shapes.title.text_frame.paragraphs[0], deck_title)
            stats["updated_shapes"] += 1
        sub_ph = _get_slide_placeholder(cover, 1)
        if deck_sub and sub_ph is not None:
            sub_tf = sub_ph.text_frame
            if sub_tf.paragraphs and sub_tf.paragraphs[0].text.strip() != deck_sub:
                _replace_pptx_paragraph_preserve_font(sub_tf.paragraphs[0], deck_sub)
                stats["updated_shapes"] += 1

    title_to_slide: Dict[str, Any] = {}
    for s in slide_list[1:]:
        if s.shapes.title and s.shapes.title.text.strip():
            title_to_slide[s.shapes.title.text.strip()] = s

    content_layout = _find_slide_layout(prs, ("タイトルとコンテンツ", "Title and Content"), 1)

    for idx, sdata in enumerate(md_slides, start=1):
        stitle = sdata["title"]
        target_slide = title_to_slide.get(stitle)
        if target_slide is None and idx < len(slide_list):
            target_slide = slide_list[idx]

        if target_slide is not None:
            stats["updated_slides"] += 1
            if target_slide.shapes.title and target_slide.shapes.title.text.strip() != stitle:
                _replace_pptx_paragraph_preserve_font(target_slide.shapes.title.text_frame.paragraphs[0], stitle)
                stats["updated_shapes"] += 1

            body_shapes = [
                sh for sh in target_slide.shapes
                if sh.has_text_frame and sh != target_slide.shapes.title
                and not (sh.is_placeholder and sh.placeholder_format.type in (13, 15, 16))
            ]
            if body_shapes and sdata["bullets"]:
                body_tf = body_shapes[0].text_frame
                for b_i, (lvl, b_txt) in enumerate(sdata["bullets"]):
                    if b_i < len(body_tf.paragraphs):
                        if body_tf.paragraphs[b_i].text.strip() != b_txt:
                            _replace_pptx_paragraph_preserve_font(body_tf.paragraphs[b_i], b_txt)
                            stats["updated_shapes"] += 1
                    else:
                        np = body_tf.add_paragraph()
                        np.text = b_txt
                        np.level = min(max(lvl, 0), 4)
                        stats["updated_shapes"] += 1

            tbl_shapes = [sh.table for sh in target_slide.shapes if sh.has_table]
            if tbl_shapes and sdata["tables"]:
                dtbl = tbl_shapes[0]
                m_rows = sdata["tables"][0]
                for r_i, m_row in enumerate(m_rows):
                    if r_i >= len(dtbl.rows):
                        break
                    for c_i, val in enumerate(m_row):
                        if c_i >= len(dtbl.columns):
                            break
                        new_v = clean_inline_md(val)
                        cell = dtbl.cell(r_i, c_i)
                        if cell.text.strip() != new_v and cell.text_frame.paragraphs:
                            _replace_pptx_paragraph_preserve_font(cell.text_frame.paragraphs[0], new_v)
                            stats["updated_shapes"] += 1
        else:
            new_s = prs.slides.add_slide(content_layout)
            if new_s.shapes.title:
                new_s.shapes.title.text = stitle
            body_ph = _get_slide_placeholder(new_s, 1)
            if body_ph is not None and sdata["bullets"]:
                tf = body_ph.text_frame
                tf.clear()
                for b_i, (lvl, b_txt) in enumerate(sdata["bullets"]):
                    p = tf.paragraphs[0] if b_i == 0 else tf.add_paragraph()
                    p.text = b_txt
                    p.level = min(max(lvl, 0), 4)
            stats["added_slides"] += 1

    out_pptx.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_pptx))
    return stats


# ---------------------------------------------------------------------------
# Excel (.xlsx) 入出力・差分パッチ
# ---------------------------------------------------------------------------

def _sanitize_sheet_title(title: str, index: int) -> str:
    cleaned = re.sub(r"[\\/*?:\[\]]", "_", clean_inline_md(title)).strip()
    return (cleaned or f"Sheet{index}")[:31]


def init_xlsx_template(path: Path) -> None:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template"
    ws.views.sheetView[0].showGridLines = True

    header_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
    header_font = Font(name=FONT_JA_SANS, size=10, bold=True, color="FFFFFF")
    data_font = Font(name=FONT_JA_SANS, size=10, bold=False, color="212529")
    thin_side = Side(border_style="thin", color="CBD5E0")
    grid_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    sample_headers = ["ID", "項目", "内容", "ステータス", "備考"]
    for col_idx, h in enumerate(sample_headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = grid_border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx in range(1, len(sample_headers) + 1):
        cell = ws.cell(row=2, column=col_idx, value="")
        cell.font = data_font
        cell.border = grid_border
        cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)

    ws.freeze_panes = "A2"
    wb.save(str(path))


def _style_and_populate_worksheet(ws: Any, rows: List[List[str]]) -> None:
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    header_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    pass_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    fail_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

    header_font = Font(name=FONT_JA_SANS, size=10, bold=True, color="FFFFFF")
    data_font = Font(name=FONT_JA_SANS, size=10, bold=False, color="212529")
    bold_font = Font(name=FONT_JA_SANS, size=10, bold=True, color="1B365D")
    thin_side = Side(border_style="thin", color="CBD5E0")
    grid_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    max_cols = max(len(r) for r in rows) if rows else 0
    col_widths = [8] * max_cols

    for r_idx, row_data in enumerate(rows, start=1):
        is_header = (r_idx == 1)
        max_lines_in_row = 1
        for c_idx in range(1, max_cols + 1):
            raw_val = row_data[c_idx - 1] if c_idx - 1 < len(row_data) else ""
            val = clean_inline_md(raw_val)
            max_lines_in_row = max(max_lines_in_row, val.count("\n") + 1)
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.border = grid_border

            if is_header:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            else:
                cell.fill = zebra_fill if r_idx % 2 == 0 else white_fill
                cell.font = bold_font if c_idx == 1 and re.match(r"^[A-Z]+-\d+", val) else data_font
                cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
                if val in ("Pass", "PASS", "Closed", "解決済", "承認済", "OK"):
                    cell.fill = pass_fill
                elif val in ("Fail", "FAIL", "Open", "未解決", "NG"):
                    cell.fill = fail_fill

            lines_in_cell = val.split("\n") if val else [""]
            longest = max(sum(2 if ord(ch) > 127 else 1 for ch in ln) for ln in lines_in_cell)
            col_widths[c_idx - 1] = max(col_widths[c_idx - 1], min(longest + 4, 55))

        ws.row_dimensions[r_idx].height = 24 if is_header else max(20, 16 * max_lines_in_row)

    for c_idx, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = width

    if len(rows) >= 1 and max_cols >= 1:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(max_cols)}{len(rows)}"


def export_md_to_xlsx(md_path: Path, out_path: Path,
                      template_path: Optional[Path] = None) -> None:
    import openpyxl

    md_text = md_path.read_text(encoding="utf-8-sig")
    _, blocks = parse_markdown(md_text)

    sheet_tables: List[Tuple[str, List[List[str]]]] = []
    current_heading = md_path.stem
    for blk in blocks:
        if blk.kind == "heading" and blk.level in (1, 2, 3):
            current_heading = blk.text
        elif blk.kind == "table" and blk.rows:
            sheet_tables.append((current_heading, blk.rows))

    if not sheet_tables:
        fallback_rows = [["セクション", "内容"]]
        sec_name = "概要"
        for blk in blocks:
            if blk.kind == "heading":
                sec_name = clean_inline_md(blk.text)
            elif blk.kind == "paragraph":
                fallback_rows.append([sec_name, clean_inline_md(blk.text)])
            elif blk.kind == "list":
                for _, itm, _ in blk.items:
                    fallback_rows.append([sec_name, clean_inline_md(itm)])
        sheet_tables.append((md_path.stem, fallback_rows))

    tpl = template_path or (DEFAULT_XLSX_TEMPLATE if DEFAULT_XLSX_TEMPLATE.is_file() else None)
    wb = openpyxl.load_workbook(str(tpl)) if (tpl and tpl.is_file()) else openpyxl.Workbook()

    default_sheets = list(wb.sheetnames)
    used_names = set()

    for idx, (heading, rows) in enumerate(sheet_tables, start=1):
        base_name = _sanitize_sheet_title(heading, idx)
        sheet_name = base_name
        counter = 2
        while sheet_name in used_names:
            suffix = f"_{counter}"
            sheet_name = base_name[:31 - len(suffix)] + suffix
            counter += 1
        used_names.add(sheet_name)

        if idx == 1 and default_sheets:
            ws = wb[default_sheets[0]]
            ws.title = sheet_name
            ws.delete_rows(1, ws.max_row + 1)
        else:
            ws = wb.create_sheet(title=sheet_name)

        _style_and_populate_worksheet(ws, rows)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))


def import_xlsx_to_md(xlsx_path: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(str(xlsx_path), data_only=True)
    lines: List[str] = [
        f"<!-- source_office: {xlsx_path.as_posix()} -->",
        f"# {xlsx_path.stem}",
        "",
    ]

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows_data: List[List[str]] = []
        for row in ws.iter_rows(values_only=True):
            if all(v is None or str(v).strip() == "" for v in row):
                continue
            cells = [str(v).strip().replace("\n", "<br>") if v is not None else "" for v in row]
            rows_data.append(cells)

        if not rows_data:
            continue

        lines.append(f"## {sheet_name}")
        lines.append("")
        col_count = max(len(r) for r in rows_data)
        header = rows_data[0] + [""] * (col_count - len(rows_data[0]))
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * col_count) + " |")
        for r in rows_data[1:]:
            padded = r + [""] * (col_count - len(r))
            lines.append("| " + " | ".join(padded) + " |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _copy_openpyxl_cell_style(src_cell: Any, dst_cell: Any) -> None:
    if src_cell.has_style:
        dst_cell.font = copy.copy(src_cell.font)
        dst_cell.fill = copy.copy(src_cell.fill)
        dst_cell.border = copy.copy(src_cell.border)
        dst_cell.alignment = copy.copy(src_cell.alignment)
        dst_cell.number_format = src_cell.number_format


def patch_xlsx_with_md(base_xlsx: Path, md_path: Path, out_xlsx: Path) -> Dict[str, int]:
    import openpyxl

    wb = openpyxl.load_workbook(str(base_xlsx))
    _, blocks = parse_markdown(md_path.read_text(encoding="utf-8-sig"))

    md_sheets: List[Tuple[str, List[List[str]]]] = []
    cur_head = ""
    for b in blocks:
        if b.kind == "heading":
            cur_head = clean_inline_md(b.text)
        elif b.kind == "table" and b.rows:
            md_sheets.append((cur_head, b.rows))

    stats = {"updated_sheets": 0, "updated_cells": 0, "added_rows": 0}

    for idx, (head_name, rows) in enumerate(md_sheets):
        ws = None
        for sname in wb.sheetnames:
            if sname == head_name or sname in head_name or head_name in sname:
                ws = wb[sname]
                break
        if ws is None and idx < len(wb.sheetnames):
            ws = wb[wb.sheetnames[idx]]
        if ws is None:
            ws = wb.create_sheet(title=_sanitize_sheet_title(head_name, idx + 1))
            _style_and_populate_worksheet(ws, rows)
            stats["updated_sheets"] += 1
            stats["added_rows"] += max(0, len(rows) - 1)
            continue

        stats["updated_sheets"] += 1
        key_to_row: Dict[str, int] = {}
        for r_i in range(2, ws.max_row + 1):
            k_val = ws.cell(row=r_i, column=1).value
            if k_val is not None and str(k_val).strip():
                key_to_row[str(k_val).strip()] = r_i

        style_ref_row = min(2, ws.max_row) if ws.max_row >= 2 else 1

        for m_i, m_row in enumerate(rows[1:], start=2):
            row_key = clean_inline_md(m_row[0]) if m_row else ""
            target_r = key_to_row.get(row_key)
            if target_r is None and m_i <= ws.max_row and not row_key:
                target_r = m_i

            if target_r is not None:
                for c_i, raw_v in enumerate(m_row, start=1):
                    new_v = clean_inline_md(raw_v)
                    cell = ws.cell(row=target_r, column=c_i)
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        continue
                    old_v = "" if cell.value is None else str(cell.value).strip()
                    if old_v != new_v:
                        cell.value = new_v
                        stats["updated_cells"] += 1
            else:
                new_r = ws.max_row + 1
                for c_i, raw_v in enumerate(m_row, start=1):
                    new_v = clean_inline_md(raw_v)
                    dst_cell = ws.cell(row=new_r, column=c_i, value=new_v)
                    src_cell = ws.cell(row=style_ref_row, column=c_i)
                    _copy_openpyxl_cell_style(src_cell, dst_cell)
                stats["added_rows"] += 1

    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_xlsx))
    return stats


# ---------------------------------------------------------------------------
# PDF (.pdf) 入出力
# ---------------------------------------------------------------------------

def _register_japanese_pdf_font() -> Tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    win_font_dir = Path(r"C:\Windows\Fonts")
    reg_candidates = [
        ("YuGothic-Reg", win_font_dir / "YuGothR.ttc", 0),
        ("Meiryo-Reg", win_font_dir / "meiryo.ttc", 0),
        ("MSGothic-Reg", win_font_dir / "msgothic.ttc", 0),
    ]
    bold_candidates = [
        ("YuGothic-Bold", win_font_dir / "YuGothB.ttc", 0),
        ("Meiryo-Bold", win_font_dir / "meiryob.ttc", 0),
    ]

    font_reg = ""
    font_bold = ""
    for name, fpath, sub_idx in reg_candidates:
        if fpath.is_file():
            try:
                pdfmetrics.registerFont(TTFont(name, str(fpath), subfontIndex=sub_idx))
                font_reg = name
                break
            except Exception:
                continue

    for name, fpath, sub_idx in bold_candidates:
        if fpath.is_file():
            try:
                pdfmetrics.registerFont(TTFont(name, str(fpath), subfontIndex=sub_idx))
                font_bold = name
                break
            except Exception:
                continue

    if not font_reg:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        font_reg = "HeiseiKakuGo-W5"
    if not font_bold:
        font_bold = font_reg

    return font_reg, font_bold


def _create_mermaid_pdf_drawing(mermaid_code: str, width_pt: float,
                                font_reg: str, font_bold: str) -> Optional[Any]:
    """Mermaid図を ReportLab のベクター図形 (Drawing) に変換する。"""
    import math
    from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
    from reportlab.lib import colors

    parsed = parse_mermaid_diagram(mermaid_code)
    layout = layout_mermaid_diagram(parsed)
    boxes = layout.get("boxes", [])
    connectors = layout.get("connectors", [])
    if not boxes:
        return None

    height_pt = max(130.0, min(340.0, width_pt * float(layout.get("aspect", 0.48))))
    d = Drawing(width_pt, height_pt)
    d.add(Rect(0, 0, width_pt, height_pt,
               fillColor=colors.HexColor("#FAFCFF"),
               strokeColor=colors.HexColor("#CBD5E0"), strokeWidth=0.6))

    # ReportLab の Drawing は左下が原点 (y=0) のため y 座標を反転する
    for conn in connectors:
        x1 = (conn["x1"] / 1000.0) * width_pt
        y1 = height_pt - (conn["y1"] / 1000.0) * height_pt
        x2 = (conn["x2"] / 1000.0) * width_pt
        y2 = height_pt - (conn["y2"] / 1000.0) * height_pt
        dash = [3, 2] if conn.get("dashed") else None
        col = colors.HexColor("#6C757D" if (conn.get("dashed") and not conn.get("directed", True)) else "#2C5282")
        d.add(Line(x1, y1, x2, y2, strokeColor=col, strokeWidth=1.1, strokeDashArray=dash))

        if conn.get("directed", True):
            ang = math.atan2(y2 - y1, x2 - x1)
            arr_len = 6.0
            ax1 = x2 - arr_len * math.cos(ang - 0.45)
            ay1 = y2 - arr_len * math.sin(ang - 0.45)
            ax2 = x2 - arr_len * math.cos(ang + 0.45)
            ay2 = y2 - arr_len * math.sin(ang + 0.45)
            d.add(Polygon([x2, y2, ax1, ay1, ax2, ay2], fillColor=col, strokeColor=col))

        lbl = conn.get("label", "").strip()
        if lbl:
            mx = (x1 + x2) / 2.0
            my = (y1 + y2) / 2.0 + (5.0 if abs(y1 - y2) < 10 else 0.0)
            d.add(String(mx, my, lbl[:24], fontName=font_reg, fontSize=7.5,
                         fillColor=colors.HexColor("#2C5282"), textAnchor="middle"))

    for b in boxes:
        bx = (b["x"] / 1000.0) * width_pt
        bw = max(42.0, (b["w"] / 1000.0) * width_pt)
        bh = max(20.0, (b["h"] / 1000.0) * height_pt)
        by = height_pt - ((b["y"] / 1000.0) * height_pt) - bh
        shp = b.get("shape", "rect")
        if shp == "participant":
            f_col, s_col, t_col = colors.HexColor("#1B365D"), colors.HexColor("#1B365D"), colors.white
        elif shp == "diamond":
            f_col, s_col, t_col = colors.HexColor("#FFF4E5"), colors.HexColor("#D97706"), colors.HexColor("#1B365D")
        elif shp == "cylinder":
            f_col, s_col, t_col = colors.HexColor("#E6F4EA"), colors.HexColor("#2E7D32"), colors.HexColor("#1B365D")
        else:
            f_col, s_col, t_col = colors.HexColor("#EBF3FA"), colors.HexColor("#2C5282"), colors.HexColor("#1B365D")

        d.add(Rect(bx, by, bw, bh, rx=4, ry=4, fillColor=f_col, strokeColor=s_col, strokeWidth=1.1))
        lines_lbl = [ln.strip() for ln in str(b.get("label", "")).split("\n") if ln.strip()]
        if not lines_lbl:
            lines_lbl = [b["id"]]
        line_h = 9.5
        start_ty = by + bh / 2.0 + ((len(lines_lbl) - 1) * line_h) / 2.0 - 3.0
        for l_i, l_txt in enumerate(lines_lbl[:3]):
            d.add(String(bx + bw / 2.0, start_ty - l_i * line_h, l_txt[:26],
                         fontName=font_bold, fontSize=8.0, fillColor=t_col, textAnchor="middle"))

    return d


def export_md_to_pdf(md_path: Path, out_path: Path,
                     title_override: Optional[str] = None) -> None:
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle
    )

    font_reg, font_bold = _register_japanese_pdf_font()
    md_text = md_path.read_text(encoding="utf-8-sig")
    meta, blocks = parse_markdown(md_text)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title_override or meta.get("title", md_path.stem),
    )

    base_styles = getSampleStyleSheet()
    st_title = ParagraphStyle(
        "JaTitle", parent=base_styles["Title"],
        fontName=font_bold, fontSize=18, leading=24,
        textColor=colors.HexColor("#1B365D"), spaceAfter=12, wordWrap="CJK"
    )
    st_h1 = ParagraphStyle(
        "JaH1", parent=base_styles["Heading1"],
        fontName=font_bold, fontSize=14, leading=20,
        textColor=colors.HexColor("#1B365D"), spaceBefore=12, spaceAfter=6, wordWrap="CJK"
    )
    st_h2 = ParagraphStyle(
        "JaH2", parent=base_styles["Heading2"],
        fontName=font_bold, fontSize=12, leading=17,
        textColor=colors.HexColor("#2C5282"), spaceBefore=10, spaceAfter=4, wordWrap="CJK"
    )
    st_h3 = ParagraphStyle(
        "JaH3", parent=base_styles["Heading3"],
        fontName=font_bold, fontSize=10.5, leading=15,
        textColor=colors.HexColor("#212529"), spaceBefore=8, spaceAfter=3, wordWrap="CJK"
    )
    st_body = ParagraphStyle(
        "JaBody", parent=base_styles["Normal"],
        fontName=font_reg, fontSize=9.5, leading=14.5,
        textColor=colors.HexColor("#212529"), spaceAfter=5, wordWrap="CJK"
    )
    st_bullet = ParagraphStyle(
        "JaBullet", parent=st_body,
        leftIndent=12, firstLineIndent=-8, spaceAfter=3
    )
    st_code = ParagraphStyle(
        "JaCode", parent=st_body,
        fontName=font_reg, fontSize=8.5, leading=12,
        backColor=colors.HexColor("#F4F6F9"), borderPadding=5, leftIndent=6, rightIndent=6
    )
    st_th = ParagraphStyle(
        "JaTH", parent=st_body,
        fontName=font_bold, fontSize=8.5, leading=12,
        textColor=colors.white, wordWrap="CJK"
    )
    st_td = ParagraphStyle(
        "JaTD", parent=st_body,
        fontName=font_reg, fontSize=8.5, leading=12,
        textColor=colors.HexColor("#212529"), wordWrap="CJK"
    )

    story: List[Any] = []
    doc_title = title_override or meta.get("title")
    if doc_title:
        story.append(Paragraph(escape(doc_title), st_title))

    usable_width = A4[0] - 36 * mm

    for blk in blocks:
        if blk.kind == "heading":
            if blk.level == 1 and doc_title and blk.text.strip() == doc_title.strip():
                doc_title = None
                continue
            st = st_h1 if blk.level == 1 else (st_h2 if blk.level == 2 else st_h3)
            story.append(Paragraph(escape(clean_inline_md(blk.text)), st))

        elif blk.kind in ("paragraph", "note"):
            story.append(Paragraph(escape(clean_inline_md(blk.text)).replace("\n", "<br/>"), st_body))

        elif blk.kind == "list":
            for indent, itm, is_ord in blk.items:
                bullet_mark = "• " if not is_ord else "1. "
                pad = "&nbsp;&nbsp;" * indent
                story.append(Paragraph(f"{pad}{bullet_mark}{escape(clean_inline_md(itm))}", st_bullet))

        elif blk.kind == "code":
            lang = blk.meta.get("lang", "").strip().lower()
            if lang == "mermaid":
                d_flow = _create_mermaid_pdf_drawing(blk.text, usable_width, font_reg, font_bold)
                if d_flow is not None:
                    story.append(d_flow)
                    story.append(Spacer(1, 8))
                    continue
            story.append(Preformatted(blk.text, st_code))
            story.append(Spacer(1, 4))

        elif blk.kind == "table" and blk.rows:
            c_cnt = max(len(r) for r in blk.rows)
            col_weights = []
            for c_i in range(c_cnt):
                max_len = 4
                for r in blk.rows:
                    cell_txt = clean_inline_md(r[c_i]) if c_i < len(r) else ""
                    for seg in cell_txt.split("\n"):
                        w = sum(2 if ord(ch) > 127 else 1 for ch in seg)
                        max_len = max(max_len, w)
                col_weights.append(min(max(max_len + 4, 11), 36))
            total_w = sum(col_weights) or 1
            col_widths = [usable_width * (w / total_w) for w in col_weights]

            tbl_data = []
            for r_i, r in enumerate(blk.rows):
                row_cells = []
                for c_i in range(c_cnt):
                    raw = r[c_i] if c_i < len(r) else ""
                    txt = escape(clean_inline_md(raw)).replace("\n", "<br/>")
                    row_cells.append(Paragraph(txt, st_th if r_i == 0 else st_td))
                tbl_data.append(row_cells)

            t = Table(tbl_data, colWidths=col_widths, repeatRows=1)
            t_style = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B365D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
            for r_i in range(1, len(tbl_data)):
                bg = colors.HexColor("#F8FAFC") if r_i % 2 == 1 else colors.white
                t_style.append(("BACKGROUND", (0, r_i), (-1, r_i), bg))
            t.setStyle(TableStyle(t_style))
            story.append(t)
            story.append(Spacer(1, 8))

    doc.build(story)


def import_pdf_to_md(pdf_path: Path) -> str:
    import pdfplumber

    lines: List[str] = [
        f"<!-- source_office: {pdf_path.as_posix()} -->",
        f"# {pdf_path.stem}",
        "",
    ]

    with pdfplumber.open(str(pdf_path)) as pdf:
        for p_idx, page in enumerate(pdf.pages, start=1):
            lines.append(f"## ページ {p_idx}")
            lines.append("")

            text = (page.extract_text() or "").strip()
            if text:
                lines.append(text)
                lines.append("")

            tables = page.extract_tables() or []
            for tbl in tables:
                cleaned_rows = []
                for row in tbl:
                    if not row or all(c is None or str(c).strip() == "" for c in row):
                        continue
                    cleaned_rows.append([
                        str(c).strip().replace("\n", "<br>") if c is not None else ""
                        for c in row
                    ])
                if cleaned_rows:
                    c_cnt = max(len(r) for r in cleaned_rows)
                    hdr = cleaned_rows[0] + [""] * (c_cnt - len(cleaned_rows[0]))
                    lines.append("| " + " | ".join(hdr) + " |")
                    lines.append("| " + " | ".join(["---"] * c_cnt) + " |")
                    for r in cleaned_rows[1:]:
                        padded = r + [""] * (c_cnt - len(r))
                        lines.append("| " + " | ".join(padded) + " |")
                    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# 省トークン自動化機能: batch-export（開発文書の一括Office変換）
# ---------------------------------------------------------------------------

def batch_export_artifacts(artifacts_dir: Path, out_dir: Path,
                           formats: List[str]) -> List[str]:
    """
    `docs/artifacts/` 内のMarkdown成果物を、LLMを介さずに一括で適切なOffice形式へ変換する。
    - SW105 / SW205 / SWP6 -> Word (.docx) および PDF (.pdf)
    - SWP6 / BUG101 / TM101 -> Excel (.xlsx)
    """
    generated: List[str] = []
    if not artifacts_dir.is_dir():
        return generated

    out_dir.mkdir(parents=True, exist_ok=True)
    md_files = sorted(artifacts_dir.glob("*.md"))

    for md_file in md_files:
        name = md_file.stem
        if name.upper() == "README" or name.startswith("REV101"):
            continue

        if "docx" in formats and name.startswith(("SW105", "SW205", "SWP6")):
            dst = out_dir / f"{name}.docx"
            export_md_to_docx(md_file, dst)
            generated.append(dst.as_posix())

        if "xlsx" in formats and name.startswith(("SWP6", "BUG101", "TM101")):
            dst = out_dir / f"{name}.xlsx"
            export_md_to_xlsx(md_file, dst)
            generated.append(dst.as_posix())

        if "pdf" in formats and name.startswith(("SW105", "SW205", "SWP6")):
            dst = out_dir / f"{name}.pdf"
            export_md_to_pdf(md_file, dst)
            generated.append(dst.as_posix())

    return generated


# ---------------------------------------------------------------------------
# 構造・レイアウト検査インスペクタ (inspect)
# ---------------------------------------------------------------------------

def inspect_office_file(path: Path, summary_only: bool = False) -> Tuple[int, str]:
    """
    Office文書またはPDFの構造サマリとレイアウト警告（文字溢れ・空ヘッダ・数式エラー等）を出力する。
    戻り値: (警告件数, レポート文字列)
    """
    ext = path.suffix.lower()
    warnings: List[str] = []
    info = [f"# Office/PDF 構造・レイアウト検査レポート: `{path.as_posix()}`"]
    summary_line = ""

    if ext in (".docx", ".dotm", ".dotx"):
        doc = open_word_document(path)
        headings = [
            f"- [{p.style.name}] {p.text.strip()}"
            for p in doc.paragraphs
            if p.text.strip() and p.style and (p.style.name == "Title" or p.style.name.lower().startswith("heading"))
        ]
        diagrams_cnt = len(doc.element.body.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pict"))
        empty_headers = 0
        for idx, t in enumerate(doc.tables, start=1):
            if t.rows:
                hdr_cells = [c.text.strip() for c in t.rows[0].cells]
                if any(c == "" for c in hdr_cells):
                    empty_headers += 1
                    warnings.append(f"表{idx}のヘッダ行に空セルがあります")
        info.append(f"- 形式: Word ({ext}) | 段落: {len(doc.paragraphs)} | 見出し: {len(headings)} | 表: {len(doc.tables)} | 図: {diagrams_cnt}")
        if headings:
            info.append("## 見出し一覧")
            info.extend(headings[:25])
        if doc.tables:
            info.append("## 表サマリ")
            for idx, t in enumerate(doc.tables, start=1):
                hdr = [c.text.strip().replace("\n", " ") for c in t.rows[0].cells] if t.rows else []
                info.append(f"- 表{idx}: {len(t.rows)}行 × {len(hdr)}列 (ヘッダ: {', '.join(hdr[:6])})")
        status = "WARN" if warnings else "OK"
        summary_line = f"OFFICE-INSPECT: {status} | format=docx | headings={len(headings)} | tables={len(doc.tables)} | diagrams={diagrams_cnt} | warnings={len(warnings)}"

    elif ext == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(str(path), data_only=False)
        formula_errors = 0
        info.append(f"- 形式: Excel (.xlsx) | シート数: {len(wb.sheetnames)} ({', '.join(wb.sheetnames)})")
        for sname in wb.sheetnames:
            ws = wb[sname]
            hdr = [str(ws.cell(row=1, column=c).value or "") for c in range(1, min(ws.max_column + 1, 10))]
            info.append(f"  - シート `{sname}`: {ws.max_row}行 × {ws.max_column}列 (先頭行: {', '.join(hdr)})")
            for row in ws.iter_rows(values_only=True):
                for val in row:
                    if isinstance(val, str) and val.startswith(("#REF!", "#NAME?", "#VALUE!", "#N/A")):
                        formula_errors += 1
        if formula_errors:
            warnings.append(f"数式エラー値が {formula_errors} 箇所検出されました")
        status = "WARN" if warnings else "OK"
        summary_line = f"OFFICE-INSPECT: {status} | format=xlsx | sheets={len(wb.sheetnames)} | warnings={len(warnings)}"

    elif ext in (".pptx", ".potx", ".potm"):
        prs = open_ppt_presentation(path)
        info.append(f"- 形式: PowerPoint ({ext}) | スライド数: {len(prs.slides)}")
        for idx, s in enumerate(prs.slides, start=1):
            stitle = s.shapes.title.text.strip() if (s.shapes.title and s.shapes.title.text.strip()) else "(無題)"
            bullet_cnt = 0
            char_cnt = 0
            tbl_cnt = 0
            diag_shp_cnt = 0
            for sh in s.shapes:
                if sh.has_table:
                    tbl_cnt += 1
                    if len(sh.table.rows) > MAX_SLIDE_TABLE_ROWS:
                        warnings.append(f"スライド{idx}: 表の行数({len(sh.table.rows)}行)が推奨上限({MAX_SLIDE_TABLE_ROWS}行)を超えています")
                elif sh.has_text_frame and sh != s.shapes.title:
                    if sh.is_placeholder and sh.placeholder_format.type in (13, 15, 16):
                        continue
                    if not sh.is_placeholder and getattr(sh, "shape_type", None) == 1:
                        # AUTO_SHAPE (1) はMermaid図形ノードとしてカウント
                        diag_shp_cnt += 1
                        continue
                    for p in sh.text_frame.paragraphs:
                        if p.text.strip():
                            bullet_cnt += 1
                            char_cnt += len(p.text.strip())
            if idx > 1 and bullet_cnt == 0 and tbl_cnt == 0 and diag_shp_cnt == 0:
                warnings.append(f"スライド{idx} ({stitle}): スライドに本文・表・図が含まれていません")
            if bullet_cnt > MAX_SLIDE_BULLETS or char_cnt > MAX_SLIDE_CHARS:
                warnings.append(f"スライド{idx} ({stitle}): 文字量({bullet_cnt}項目/{char_cnt}文字)が多く枠溢れの恐れがあります")
            info.append(f"  - スライド {idx}: {stitle} (箇条書き: {bullet_cnt}, 文字数: {char_cnt}, 表: {tbl_cnt}, 図形ノード: {diag_shp_cnt})")
        status = "WARN" if warnings else "OK"
        summary_line = f"OFFICE-INSPECT: {status} | format=pptx | slides={len(prs.slides)} | warnings={len(warnings)}"

    elif ext == ".pdf":
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            info.append(f"- 形式: PDF (.pdf) | ページ数: {len(pdf.pages)}")
            total_tables = 0
            for idx, page in enumerate(pdf.pages[:20], start=1):
                txt = (page.extract_text() or "").strip()
                first_line = txt.splitlines()[0] if txt else "(テキストなし)"
                tbls = page.extract_tables() or []
                total_tables += len(tbls)
                if not txt:
                    warnings.append(f"ページ{idx}: テキストが抽出できません（画像スキャンPDFの可能性があります）")
                info.append(f"  - ページ {idx}: {len(txt)}文字, 表{len(tbls)}件 (先頭: {first_line[:50]})")
            status = "WARN" if warnings else "OK"
            summary_line = f"OFFICE-INSPECT: {status} | format=pdf | pages={len(pdf.pages)} | tables={total_tables} | warnings={len(warnings)}"
    else:
        raise ValueError(f"未対応の拡張子です: {ext}")

    if warnings:
        info.append("## レイアウト・構造警告")
        for w in warnings:
            info.append(f"- [WARN] {w}")
    info.append("")
    info.append(summary_line)

    if summary_only:
        return len(warnings), summary_line
    return len(warnings), "\n".join(info)


# ---------------------------------------------------------------------------
# テンプレート初期化 (Normal.dotm / Blank.potx からの標準テンプレート整備)
# ---------------------------------------------------------------------------

def init_templates(out_dir: Path) -> List[str]:
    """
    `Normal.dotm` と `Blank.potx` が存在する場合はそれらから `template_document.docx` / `template_slide.pptx`
    を同期生成し、Excel用の `template_sheet.xlsx` も生成する。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    created: List[str] = []

    docx_p = out_dir / "template_document.docx"
    doc = open_word_document(out_dir / "Normal.dotm" if (out_dir / "Normal.dotm").is_file() else None)
    doc.save(str(docx_p))
    created.append(docx_p.as_posix())

    xlsx_p = out_dir / "template_sheet.xlsx"
    init_xlsx_template(xlsx_p)
    created.append(xlsx_p.as_posix())

    pptx_p = out_dir / "template_slide.pptx"
    prs = open_ppt_presentation(out_dir / "Blank.potx" if (out_dir / "Blank.potx").is_file() else None)
    prs.save(str(pptx_p))
    created.append(pptx_p.as_posix())

    return created


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DADA Process Office文書・PDF 決定論的入出力ツール (Word / Excel / PowerPoint / PDF)"
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # init-templates
    p_init = sub.add_parser("init-templates", help="Officeテンプレート一式を初期化する（Normal.dotm / Blank.potx 対応）")
    p_init.add_argument("--out-dir", default=str(DEFAULT_TEMPLATE_DIR), help="テンプレート格納ディレクトリ")

    # import
    p_imp = sub.add_parser("import", help="既存のOffice文書またはPDF (.docx/.xlsx/.pptx/.pdf) をMarkdown (.md) に変換する")
    p_imp.add_argument("--input", required=True, help="入力ファイルパス (.docx / .xlsx / .pptx / .pdf)")
    p_imp.add_argument("--output", required=True, help="出力Markdownファイルパス (.md)")
    p_imp.add_argument("--summary", action="store_true", help="1行サマリのみ出力する（省トークン用）")

    # export
    p_exp = sub.add_parser("export", help="Markdown (.md) をOffice文書またはPDF (.docx/.xlsx/.pptx/.pdf) に変換する")
    p_exp.add_argument("--input", required=True, help="入力Markdownファイルパス (.md)")
    p_exp.add_argument("--output", required=True, help="出力ファイルパス (.docx / .xlsx / .pptx / .pdf)")
    p_exp.add_argument("--template", default=None, help="適用するOfficeテンプレート（省略時は Normal.dotm / Blank.potx / template_sheet.xlsx）")
    p_exp.add_argument("--title", default=None, help="文書タイトルの上書き指定")
    p_exp.add_argument("--summary", action="store_true", help="1行サマリのみ出力する（省トークン用）")

    # patch
    p_pat = sub.add_parser("patch", help="既存のOffice文書 (.docx/.xlsx/.pptx) の書式を保持したままMarkdownの変更を差分反映する")
    p_pat.add_argument("--base", required=True, help="ベースとなる既存Office文書 (.docx / .xlsx / .pptx)")
    p_pat.add_argument("--input", required=True, help="改訂後のMarkdownファイルパス (.md)")
    p_pat.add_argument("--output", required=True, help="差分反映後の出力Office文書パス")
    p_pat.add_argument("--summary", action="store_true", help="1行サマリのみ出力する（省トークン用）")

    # batch-export
    p_bat = sub.add_parser("batch-export", help="docs/artifacts 内のMarkdown成果物を一括でOffice文書に変換する（LLM不要）")
    p_bat.add_argument("--artifacts-dir", default="docs/artifacts", help="入力Markdownディレクトリ")
    p_bat.add_argument("--out-dir", default="docs/artifacts/office", help="Office文書出力先ディレクトリ")
    p_bat.add_argument("--formats", default="docx,xlsx,pdf", help="出力形式のカンマ区切り (docx,xlsx,pdf)")
    p_bat.add_argument("--summary", action="store_true", help="1行サマリのみ出力する（省トークン用）")

    # inspect
    p_ins = sub.add_parser("inspect", help="Office文書またはPDFの構造とレイアウト溢れを検査する")
    p_ins.add_argument("--input", required=True, help="検査対象ファイルパス (.docx / .xlsx / .pptx / .pdf)")
    p_ins.add_argument("--summary", action="store_true", help="1行サマリのみ出力する（省トークン用）")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    try:
        if args.subcommand == "init-templates":
            created = init_templates(Path(args.out_dir))
            print(f"OFFICE-INIT: OK | files={len(created)} | {', '.join(created)}")
            return 0

        elif args.subcommand == "import":
            in_path = Path(args.input)
            out_path = Path(args.output)
            if not in_path.is_file():
                print(f"[ERROR] 入力ファイルが存在しません: {in_path}", file=sys.stderr)
                return 2
            ext = in_path.suffix.lower()
            if ext in (".docx", ".dotm", ".dotx"):
                md_content = import_docx_to_md(in_path)
            elif ext == ".xlsx":
                md_content = import_xlsx_to_md(in_path)
            elif ext in (".pptx", ".potx", ".potm"):
                md_content = import_pptx_to_md(in_path)
            elif ext == ".pdf":
                md_content = import_pdf_to_md(in_path)
            else:
                print(f"[ERROR] 未対応の入力形式です: {ext}", file=sys.stderr)
                return 2
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md_content, encoding="utf-8")
            line_cnt = len(md_content.splitlines())
            print(f"OFFICE-IMPORT: OK | in={in_path.as_posix()} | out={out_path.as_posix()} | lines={line_cnt}")
            return 0

        elif args.subcommand == "export":
            in_path = Path(args.input)
            out_path = Path(args.output)
            tpl_path = Path(args.template) if args.template else None
            if not in_path.is_file():
                print(f"[ERROR] 入力Markdownファイルが存在しません: {in_path}", file=sys.stderr)
                return 2
            ext = out_path.suffix.lower()
            if ext == ".docx":
                export_md_to_docx(in_path, out_path, tpl_path, args.title)
            elif ext == ".xlsx":
                export_md_to_xlsx(in_path, out_path, tpl_path)
            elif ext == ".pptx":
                export_md_to_pptx(in_path, out_path, tpl_path, args.title)
            elif ext == ".pdf":
                export_md_to_pdf(in_path, out_path, args.title)
            else:
                print(f"[ERROR] 未対応の出力形式です: {ext}", file=sys.stderr)
                return 2
            warn_cnt, summary_str = inspect_office_file(out_path, summary_only=True)
            print(f"OFFICE-EXPORT: OK | in={in_path.as_posix()} | out={out_path.as_posix()} | {summary_str}")
            return 0

        elif args.subcommand == "patch":
            base_path = Path(args.base)
            in_path = Path(args.input)
            out_path = Path(args.output)
            if not base_path.is_file() or not in_path.is_file():
                print("[ERROR] --base または --input のファイルが存在しません", file=sys.stderr)
                return 2
            ext = base_path.suffix.lower()
            if ext in (".docx", ".dotm", ".dotx"):
                stats = patch_docx_with_md(base_path, in_path, out_path)
            elif ext == ".xlsx":
                stats = patch_xlsx_with_md(base_path, in_path, out_path)
            elif ext in (".pptx", ".potx", ".potm"):
                stats = patch_pptx_with_md(base_path, in_path, out_path)
            else:
                print(f"[ERROR] patch未対応の形式です: {ext}", file=sys.stderr)
                return 2
            print(f"OFFICE-PATCH: OK | base={base_path.as_posix()} | out={out_path.as_posix()} | stats={stats}")
            return 0

        elif args.subcommand == "batch-export":
            fmts = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
            generated = batch_export_artifacts(Path(args.artifacts_dir), Path(args.out_dir), fmts)
            print(f"OFFICE-BATCH: OK | count={len(generated)} | files={', '.join(generated) if generated else 'none'}")
            return 0

        elif args.subcommand == "inspect":
            in_path = Path(args.input)
            if not in_path.is_file():
                print(f"[ERROR] 検査対象ファイルが存在しません: {in_path}", file=sys.stderr)
                return 2
            warn_cnt, report = inspect_office_file(in_path, summary_only=args.summary)
            print(report)
            return 1 if warn_cnt > 0 else 0

    except Exception as exc:
        print(f"[ERROR] 実行エラー: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
