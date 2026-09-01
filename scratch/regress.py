"""tools/dada_check.py の回帰テスト（開発者向け。DADAプロセスの成果物ではない）

実行方法:
    python scratch/regress.py

合成した最小の成果物セットに対して dada_check.py を実行し、以下を検証する。

  1. 従来型プログラム開発（SW205に「成果物パス」欄なし）の健全な成果物が
     終了コード 0 になること。ソースツリー走査による従来の照合経路が
     壊れていないことを保証する（後方互換性の回帰検出）。
  2. エージェント定義開発（SW205に「成果物パス」を宣言）の健全な成果物が
     終了コード 0 になること。成果物が `.agents/` `tools/` 配下という
     走査除外ディレクトリにあっても照合が通ることを保証する。
  3. 宣言された成果物パスの実体を削除すると High として検出され、
     終了コード 1 になること。照合が形骸化していないことを保証する。
"""
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECK = REPO / "tools" / "dada_check.py"

SW105 = """# SW105 ソフトウェア要求仕様書

## 1. はじめに
### 1.1 目的
本書は対象システムの要求を定義する。

## 2. 全体概要
本システムは受注データを登録する。

## 3. 機能要求
#### REQ-001: 受注登録
- **概要**: 利用者が受注データを登録できる。
- **検証条件**: 必須項目をすべて入力して登録すると、HTTP 201 を返し、IDが払い出される。

#### REQ-002: 受注照会
- **概要**: 利用者が受注IDで1件を照会できる。
- **検証条件**: 存在するIDを指定すると HTTP 200 と該当1件を返す。

## 4. 非機能要求
### 4.1 性能
登録処理は1件あたり500ミリ秒以内に完了する。

## 5. 制約条件
Python 3.11 を使用する。

## 6. 用語定義
| 用語 | 定義 |
| :--- | :--- |
| 受注 | 顧客からの注文1件 |
"""

SWP6 = """# SWP6 ソフトウェア総合テスト仕様書・報告書

## 1. はじめに
### 1.1 目的
本書は総合テストの仕様と結果を記録する。

## 2. テスト対象
受注APIの全機能を対象とする。

## 3. テスト方針
自動テストを基本とする。

## 4. テスト項目
| テストID | 対象要件 | シナリオ | 前提条件 | 入力データ | 期待される出力 | 実行区分 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| TC-001 | REQ-001 | 必須項目をすべて入力して受注を登録する | APIが起動している | customer=c1 | HTTP 201 とIDが返る | 自動 |
| TC-002 | REQ-002 | 存在する受注IDで1件を照会する | 受注1件が登録済み | order_id=1 | HTTP 200 と該当1件が返る | 自動 |

## 5. テスト結果
未実施。

## 6. 総合評価
未実施。
"""

SW205_PROGRAM = """# SW205 ソフトウェアアーキテクチャ設計書

## 1. はじめに
### 1.1 目的
本書はアーキテクチャを定義する。

## 2. アーキテクチャ概要
レイヤードアーキテクチャを採用する。

## 3. ユニット定義
#### UNIT-001: 受注登録ハンドラ
- **責務**: 受注登録リクエストを検証して保存する。
- **対応要求**: REQ-001
- **公開インターフェース**: create_order(payload: dict) -> dict / 必須項目欠落時は ValueError
- **依存先**: UNIT-002
- **検証条件**: TC-001 が Pass すること。

#### UNIT-002: 受注リポジトリ
- **責務**: 受注データを永続化して読み出す。
- **対応要求**: REQ-001, REQ-002
- **公開インターフェース**: save(order: dict) -> str / find(order_id: str) -> dict
- **依存先**: なし
- **検証条件**: TC-002 が Pass すること。

## 4. データ設計
受注テーブルを1つ持つ。

## 5. インターフェース設計
REST APIで公開する。

## 6. 非機能要求への対応
インメモリキャッシュで500ミリ秒以内を満たす。

## 7. テスト容易性
全ユニットを依存注入で差し替え可能にする。

## 8. トレーサビリティ
| REQ-ID | UNIT-ID | TC-ID |
| :--- | :--- | :--- |
| REQ-001 | UNIT-001, UNIT-002 | TC-001 |
| REQ-002 | UNIT-002 | TC-002 |
"""

SRC_HANDLER = '''"""受注登録ハンドラ

対応UNIT-ID: UNIT-001
対応REQ-ID: REQ-001
"""


def create_order(payload):
    if not payload.get("customer"):
        raise ValueError("customer is required")
    return {"id": "1"}
'''

SRC_REPO = '''"""受注リポジトリ

対応UNIT-ID: UNIT-002
対応REQ-ID: REQ-001, REQ-002
"""

_STORE = {}


def save(order):
    _STORE["1"] = order
    return "1"


def find(order_id):
    return _STORE[order_id]
'''

TEST_SRC = '''"""受注APIの総合テスト

対応TC-ID: TC-001, TC-002
"""
from app.handler import create_order
from app.repository import find, save


def test_create_order():
    """TC-001"""
    assert create_order({"customer": "c1"})["id"] == "1"


def test_find_order():
    """TC-002"""
    save({"customer": "c1"})
    assert find("1")["customer"] == "c1"
'''

SW205_AGENT = """# SW205 ソフトウェアアーキテクチャ設計書

## 1. はじめに
### 1.1 目的
本書はエージェント定義のアーキテクチャを定義する。

## 2. アーキテクチャ概要
自然言語レイヤーとプログラムレイヤーの二重構造を採用する。

## 3. ユニット定義
#### UNIT-001: 議事録生成スキル
- **責務**: 文字起こしから議事録を生成する手順を規定する。
- **レイヤー**: 自然言語
- **成果物パス**: `.agents/skills/minutes-writer/SKILL.md`
- **対応要求**: REQ-001
- **公開インターフェース**: スキル名 minutes-writer / 入力は文字起こしテキスト / 出力は議事録Markdown
- **依存先**: UNIT-002
- **検証条件**: EV-001 の合格率が90パーセント以上であること。

#### UNIT-002: 議事録構文チェッカー
- **責務**: 生成された議事録の必須節の有無を決定論的に検証する。
- **レイヤー**: プログラム
- **成果物パス**: `tools/minutes_check.py`
- **対応要求**: REQ-002
- **公開インターフェース**: python tools/minutes_check.py <path> / 終了コード 0 は合格、1 は不合格
- **依存先**: なし
- **検証条件**: TC-002 が Pass すること。

## 4. データ設計
議事録Markdownの節構造を定義する。

## 5. インターフェース設計
ACI仕様として、コマンド行と終了コードを規定する。

## 6. 非機能要求への対応
参照ファイルを分割してコンテキスト消費を抑える。

## 7. テスト容易性
プログラムレイヤーを独立コマンドとして起動可能にする。

## 8. トレーサビリティ
| REQ-ID | UNIT-ID | TC-ID |
| :--- | :--- | :--- |
| REQ-001 | UNIT-001 | TC-001 |
| REQ-002 | UNIT-002 | TC-002 |
"""

SKILL_MD = """---
name: minutes-writer
description: 文字起こしから議事録を生成するときに使用します。
---

# 議事録生成スキル

対応UNIT-ID: UNIT-001

## 作業手順
1. 文字起こしを読み、決定事項と宿題を抽出する。
2. `python tools/minutes_check.py <出力パス>` を実行し、終了コード0を確認する。

## 禁止事項
- 文字起こしに存在しない決定事項を書いてはならない。
"""

TOOL_PY = '''"""議事録構文チェッカー

対応UNIT-ID: UNIT-002
対応REQ-ID: REQ-002
"""
import sys


def main(path):
    text = open(path, encoding="utf-8").read()
    return 0 if "## 決定事項" in text else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
'''

AGENT_TEST = '''"""議事録構文チェッカーのテスト

対応TC-ID: TC-002
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import minutes_check


def test_detects_missing_section(tmp_path):
    """TC-002"""
    p = tmp_path / "m.md"
    p.write_text("## 概要", encoding="utf-8")
    assert minutes_check.main(str(p)) == 1
'''

SWP6_AGENT = SWP6.replace(
    "| TC-001 | REQ-001 | 必須項目をすべて入力して受注を登録する | APIが起動している"
    " | customer=c1 | HTTP 201 とIDが返る | 自動 |",
    "| TC-001 | REQ-001 | 文字起こしから議事録を生成する | 文字起こしを用意"
    " | sample_transcript.txt | 決定事項節に3件が列挙される（EV-001） | 評価 |",
).replace(
    "| TC-002 | REQ-002 | 存在する受注IDで1件を照会する | 受注1件が登録済み"
    " | order_id=1 | HTTP 200 と該当1件が返る | 自動 |",
    "| TC-002 | REQ-002 | 必須節が欠けた議事録を検査する | 議事録Markdownを用意"
    " | 決定事項節なしのMarkdown | 終了コード1を返す | 自動 |",
)


def write(base: Path, relpath: str, content: str) -> None:
    target = base / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def build_program_repo(base: Path) -> None:
    write(base, "docs/artifacts/SW105_ソフトウェア要求仕様書.md", SW105)
    write(base, "docs/artifacts/SWP6_ソフトウェア総合テスト仕様書・報告書.md", SWP6)
    write(base, "docs/artifacts/SW205_ソフトウェアアーキテクチャ設計書.md", SW205_PROGRAM)
    write(base, "app/handler.py", SRC_HANDLER)
    write(base, "app/repository.py", SRC_REPO)
    write(base, "tests/test_orders.py", TEST_SRC)


def build_agent_repo(base: Path) -> None:
    write(base, "docs/artifacts/SW105_ソフトウェア要求仕様書.md", SW105)
    write(base, "docs/artifacts/SWP6_ソフトウェア総合テスト仕様書・報告書.md", SWP6_AGENT)
    write(base, "docs/artifacts/SW205_ソフトウェアアーキテクチャ設計書.md", SW205_AGENT)
    write(base, ".agents/skills/minutes-writer/SKILL.md", SKILL_MD)
    write(base, "tools/minutes_check.py", TOOL_PY)
    write(base, "tests/test_minutes_check.py", AGENT_TEST)


def run(script: Path, base: Path):
    proc = subprocess.run(
        [sys.executable, str(script), "all", "--root", str(base), "--no-report"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def show_high(out: str) -> None:
    for line in out.splitlines():
        if "[High]" in line:
            print("    {}".format(line.strip()))


def main() -> int:
    failures = []

    # --- 1. 従来型プログラム開発（ソースツリー走査による照合） ---
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "prog"
        base.mkdir()
        build_program_repo(base)
        rc_prog, out_prog = run(CHECK, base)

    print("=== [1] 従来型プログラム開発（成果物パス欄なし） ===")
    print("  exit={} （期待値: 0）".format(rc_prog))
    if rc_prog != 0:
        failures.append("従来型プログラムの健全な成果物で High が出る（exit={}）".format(rc_prog))
        show_high(out_prog)
    else:
        print("  判定: OK（ソースツリー走査による従来の照合経路が健全）")

    # --- 2 & 3. エージェント定義開発（宣言パスによる照合） ---
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "agent"
        base.mkdir()
        build_agent_repo(base)
        rc_agent, out_agent = run(CHECK, base)

        # 宣言された成果物パスの実体を削除して、検出されることを確認する
        (base / ".agents/skills/minutes-writer/SKILL.md").unlink()
        rc_broken, out_broken = run(CHECK, base)

    print("\n=== [2] エージェント定義開発（成果物パス宣言あり） ===")
    print("  exit={} （期待値: 0）".format(rc_agent))
    if rc_agent != 0:
        failures.append("エージェント定義の健全な成果物で High が出る（exit={}）".format(rc_agent))
        show_high(out_agent)
    else:
        print("  判定: OK（.agents/ と tools/ 配下でも宣言パス照合が通る）")

    print("\n=== [3] 宣言された成果物パスの実体を削除 ===")
    print("  exit={} （期待値: 1）".format(rc_broken))
    detected = "成果物パスが存在しない" in out_broken
    if detected and rc_broken == 1:
        print("  判定: OK（削除を High として検出。照合が形骸化していない）")
    else:
        failures.append("成果物パスの欠落を検出できない（exit={}）".format(rc_broken))

    print("\n" + "=" * 60)
    if failures:
        print("RESULT: NG")
        for f in failures:
            print("  - {}".format(f))
        return 1
    print("RESULT: OK（従来経路 / 宣言パス経路 / 欠落検出 のすべてが期待どおり）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
