"""新規・改訂したドキュメント内のリポジトリ内パス参照が実在するかを確認する（開発者向け）

実行方法:
    python scratch/linkcheck.py
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

TARGETS = [
    "README.md",
    ".agents/AGENTS.md",
    "docs/examples/prompts_usage.md",
    "docs/examples/README.md",
    "docs/guidelines/agent_design_principles.md",
    "docs/guidelines/README.md",
    "docs/templates/README.md",
    "docs/templates/agent/README.md",
    "docs/templates/agent/phase1_agent_requirements_template.md",
    "docs/templates/agent/phase2_agent_eval_spec_template.md",
    "docs/templates/agent/phase3_agent_design_template.md",
    "docs/process/README.md",
    "docs/process/autoloop_log.md",
    "docs/process/eval_report.md",
    "tools/README.md",
    "scratch/README.md",
]
TARGETS += [str(p.relative_to(REPO)).replace("\\", "/")
            for p in sorted((REPO / ".agents/skills").glob("*/SKILL.md"))]

# 拡張子を持つ、リポジトリ内パスらしいトークン（ASCIIのみ。日本語文が続く箇所は拾わない）
TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9./_-])((?:\.agents|docs|tools|tests|scratch)"
    r"/[A-Za-z0-9./_<>-]*\.[A-Za-z0-9]{1,5})"
)
# 出力先・記入例・プレースホルダは実在チェックの対象外
SKIP_PREFIX = ("docs/artifacts/", "docs/minutes/")
SKIP_HINT = ("記入例", "（例", "例:", "例）", "<name>", "<ペルソナ名>", "MyCompany",
             "<path>", "YYYY", "SPEC.md")
# 記入例ブロック（`#### UNIT-EX` / `#### REQ-EX` 等）の配下は例示のため対象外
EX_BLOCK_RE = re.compile(r"^#{2,6}\s+[A-Z]+-EX")
HEADING_RE = re.compile(r"^#{2,6}\s")


def main() -> int:
    missing = []
    checked = 0
    for rel in TARGETS:
        path = REPO / rel
        if not path.is_file():
            missing.append((rel, "<対象ファイル自体が存在しない>", 0))
            continue
        in_example_block = False
        for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").split("\n"), 1):
            if EX_BLOCK_RE.match(line):
                in_example_block = True
                continue
            if HEADING_RE.match(line):
                in_example_block = False
            if in_example_block or any(h in line for h in SKIP_HINT):
                continue
            for token in TOKEN_RE.findall(line):
                if token.startswith(SKIP_PREFIX) or "<" in token or ">" in token:
                    continue
                checked += 1
                if not (REPO / token).exists():
                    missing.append((rel, token, lineno))

    print("検査したパス参照: {} 件（対象 {} ファイル）".format(checked, len(TARGETS)))
    if missing:
        print("\n存在しない参照:")
        for rel, token, lineno in missing:
            print("  {}:{} -> {}".format(rel, lineno, token))
        print("\nRESULT: NG（{} 件）".format(len(missing)))
        return 1
    print("RESULT: OK（すべての参照が実在）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
