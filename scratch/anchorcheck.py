"""Markdown内の見出しリンク（#アンカー）が実在する見出しを指しているかを確認する（開発者向け）

実行方法:
    python scratch/anchorcheck.py

GitHubのアンカー生成規則を再現する。
  1. 見出しテキストを小文字化する
  2. 英数字・アンダースコア・ハイフン・空白・Unicode文字以外（句読点等）を削除する
  3. 空白をハイフンに置換する
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


def slugify(text: str) -> str:
    # インラインの装飾・コード記法を落とす
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]*)\*", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.lower()
    out = []
    for ch in text:
        if ch.isalnum() or ch in "_- ":
            out.append(ch)
        elif unicodedata.category(ch).startswith("M"):
            out.append(ch)
        # それ以外（句読点・記号）は削除
    return "".join(out).strip().replace(" ", "-")


def main() -> int:
    broken = []
    checked = 0
    for rel in TARGETS:
        path = REPO / rel
        if not path.is_file():
            broken.append((rel, "<ファイル自体が存在しない>", 0, []))
            continue
        lines = path.read_text(encoding="utf-8-sig").split("\n")

        anchors = set()
        in_code = False
        for line in lines:
            if line.lstrip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            m = HEADING_RE.match(line)
            if m:
                anchors.add(slugify(m.group(2)))

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

    print("検査した見出しリンク: {} 件（対象 {} ファイル）".format(checked, len(TARGETS)))
    if broken:
        print("\nリンク切れ:")
        for rel, anchor, lineno, anchors in broken:
            print("  {}:{} -> #{}".format(rel, lineno, anchor))
            near = [a for a in anchors if a and (a[:6] in anchor or anchor[:6] in a)]
            if near:
                print("    候補: {}".format(", ".join("#" + a for a in near[:3])))
        print("\nRESULT: NG（{} 件）".format(len(broken)))
        return 1
    print("RESULT: OK（すべての見出しリンクが実在）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
