"""Markdown内の見出しリンク（#アンカー）が実在する見出しを指しているかを確認する（開発者向け）

実行方法:
    python scratch/anchorcheck.py

GitHubのアンカー生成規則を再現する。
  1. 見出しテキストを小文字化する
  2. 英数字・アンダースコア・ハイフン・空白・Unicode文字以外（句読点等）を削除する
  3. 空白をハイフンに置換する
  4. 絵文字・記号・結合文字（異体字セレクタ U+FE0E / U+FE0F を含む）は削除する

加えて、HTMLの明示アンカー（`<a id="...">` / `<a name="...">`）も収集する。
README.md は日本語見出しの安定リンクのため HTML id を使っている。
見出しスラッグだけを見ると誤ってリンク切れと判定してしまう。
"""
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

TARGETS = [
    "README.md",
    "docs/examples/prompts_usage.md",
    "docs/examples/README.md",
    "docs/guidelines/agent_design_principles.md",
    "docs/templates/agent/README.md",
    "tools/README.md",
    "docs/process/README.md",
]

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
# 同一ファイル内の見出しリンク [表示](#anchor)
LINK_RE = re.compile(r"\[[^\]]*\]\(#([^)]+)\)")
# <a id="..."> / <a name="...">（属性順は問わない）
HTML_ANCHOR_RE = re.compile(
    r"<a\s+(?:[^>]*?\s+)?(?:id|name)\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
# 記号・結合文字・制御文字は GitHub スラッグに残さない
_SKIP_CATEGORIES = frozenset({
    "So", "Sk", "Sm", "Sc",  # 記号（絵文字の本体は So が多い）
    "Mn", "Mc", "Me",        # 結合文字（異体字セレクタは Mn）
    "Cc", "Cf", "Cs", "Co", "Cn",
})
_VARIATION_SELECTORS = frozenset({"\ufe0e", "\ufe0f"})


def _configure_stdio() -> None:
    """Windows の cp932 コンソールでも検査結果を最後まで出す。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.buffer.write(
            (text + "\n").encode(encoding, errors="replace")
        )


def slugify(text: str) -> str:
    # インラインの装飾・コード記法を落とす
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]*)\*", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.lower()
    out = []
    for ch in text:
        if ch in _VARIATION_SELECTORS:
            continue
        category = unicodedata.category(ch)
        if category in _SKIP_CATEGORIES:
            continue
        if ch.isalnum() or ch in "_- ":
            out.append(ch)
        # それ以外（句読点・記号）は削除
    return "".join(out).strip().replace(" ", "-")


def collect_anchors(lines: list[str]) -> set[str]:
    """見出しスラッグと HTML 明示 id の和集合を返す。"""
    anchors: set[str] = set()
    in_code = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        heading = HEADING_RE.match(line)
        if heading:
            anchors.add(slugify(heading.group(2)))
        for html_id in HTML_ANCHOR_RE.findall(line):
            anchors.add(html_id)
            lowered = html_id.lower()
            if lowered != html_id:
                anchors.add(lowered)
    return anchors


def _self_check() -> None:
    """slugify が絵文字・異体字セレクタを残さないこと。HTML id を収集すること。"""
    slug = slugify("🖥️ Antigravity 2.0 の左欄とサブエージェント")
    if "\ufe0f" in slug or "\ufe0e" in slug:
        raise AssertionError("slugify が異体字セレクタを残している: " + repr(slug))
    expected = "antigravity-20-の左欄とサブエージェント"
    if slug != expected:
        raise AssertionError(
            "slugify の結果が想定と違う: got {} expected {}".format(
                repr(slug), repr(expected)
            )
        )
    html_ids = collect_anchors([
        '<a id="作業ブランチ"></a>',
        "### Step 4: 開発の前に作業ブランチを切る",
    ])
    if "作業ブランチ" not in html_ids:
        raise AssertionError("HTML id を収集できていない: " + repr(sorted(html_ids)))
    if "step-4-開発の前に作業ブランチを切る" not in html_ids:
        raise AssertionError("見出しスラッグを収集できていない: " + repr(sorted(html_ids)))


def main() -> int:
    _configure_stdio()
    try:
        _self_check()
    except AssertionError as exc:
        _safe_print("SELFCHECK: NG（{}）".format(exc))
        return 2

    broken = []
    checked = 0
    for rel in TARGETS:
        path = REPO / rel
        if not path.is_file():
            broken.append((rel, "<ファイル自体が存在しない>", 0, []))
            continue
        lines = path.read_text(encoding="utf-8-sig").split("\n")
        anchors = collect_anchors(lines)

        in_code = False
        for lineno, line in enumerate(lines, 1):
            if line.lstrip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            for anchor in LINK_RE.findall(line):
                checked += 1
                if anchor not in anchors:
                    broken.append((rel, anchor, lineno, sorted(anchors)))

    _safe_print("検査した見出しリンク: {} 件（対象 {} ファイル）".format(checked, len(TARGETS)))
    if broken:
        _safe_print("\nリンク切れ:")
        for rel, anchor, lineno, anchors in broken:
            _safe_print("  {}:{} -> #{}".format(rel, lineno, anchor))
            near = [a for a in anchors if a and (a[:6] in anchor or anchor[:6] in a)]
            if near:
                _safe_print("    候補: {}".format(", ".join("#" + a for a in near[:3])))
        _safe_print("\nRESULT: NG（{} 件）".format(len(broken)))
        return 1
    _safe_print("RESULT: OK（すべての見出しリンクが実在）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
