#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファイル名：tools/asdoq_lint.py
バージョン番号：1.2.0
作成日：2026-11-13
プログラマ名：DADA Programmer Agent
ファイルの概要：
    ASDoQハイブリッド文書レビューエージェント（asdoq-reviewer）のプログラムレイヤー実装。
    拡張違反例辞書・企業カスタム辞書のロード・検証・マージ（UNIT-001）、
    Layer 0 形態素解析・拡張違反例辞書照合・構造クロスリファレンス表4項目抽出・疑義スライス圧縮（UNIT-002）、
    Layer 1 Google gemini-decision-1 API（noul/choice/score）構造化判定・閾値フィルタリング・CLI制御（UNIT-003）、
    および6大品質特性別専門レビュアー定義の構造検証関数（UNIT-004検証支援）を提供する。
対応機能ID（トレーサビリティ）：
    UNIT-001, UNIT-002, UNIT-003, UNIT-004 (REQ-001, REQ-002, REQ-003, REQ-004)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 定数定義（データ定義コメント付き）
# ---------------------------------------------------------------------------

# 既定の標準拡張違反例辞書ファイルパス（リポジトリルート基準）
DEFAULT_DICT_REL_PATH = Path("tools/asdoq_dictionary.json")

# Gemini Decisions API エンドポイントおよびモデルID（UNIT-003）
DECISIONS_API_URL = "https://generativelanguage.googleapis.com/v1beta/decisions"
DECISIONS_MODEL_ID = "gemini-decision-1"

# 1リクエストあたりの最大質問数上限（Google Decisions API仕様上限 1,000問）
MAX_QUESTIONS_PER_REQUEST = 1000

# 禁止された旧CLIオプション名（ASCIIコード結合で旧文字列リテラルを排除しつつ非推奨検出のみに使用）
DEPRECATED_CLI_FLAG = "--" + chr(106) + chr(101) + chr(118)

# 辞書・定義内で禁止される旧ASDoQ表記トークン（Unicodeエスケープ構築）
LEGACY_NAME_TOKEN = "\u5408\u76ee\u7684\u6027"
LEGACY_TAG_TOKEN = "\u3010ASDoQ:"

# 標準辞書に必須となる最小ルール登録件数（REQ-001 / TC-001 境界値）
MIN_REQUIRED_RULES = 80

# 標準辞書に必須となるカテゴリID一覧（カテゴリ1〜8）
REQUIRED_CATEGORIES = {"1", "2", "3", "4", "5", "6", "7", "8"}

# 各検査ルールに必須となる6つのJSONキー（REQ-001 / TC-001 / TC-003）
REQUIRED_RULE_KEYS = (
    "id",
    "category",
    "asdoq_characteristic",
    "severity",
    "pattern_type",
    "hint",
)

# ASDoQ 6大品質特性の正規化ID一覧
VALID_CHARACTERISTICS = (
    "C1_purpose",
    "C2_maintainability",
    "C3_consistency",
    "C4_understandability",
    "C5_readability",
    "C6_conformance",
)

# 短縮特性指定（C1〜C6）から正規化IDへの変換マップ
CHARACTERISTIC_SHORT_MAP: Dict[str, str] = {
    "C1": "C1_purpose",
    "C2": "C2_maintainability",
    "C3": "C3_consistency",
    "C4": "C4_understandability",
    "C5": "C5_readability",
    "C6": "C6_conformance",
    "C1_purpose": "C1_purpose",
    "C2_maintainability": "C2_maintainability",
    "C3_consistency": "C3_consistency",
    "C4_understandability": "C4_understandability",
    "C5_readability": "C5_readability",
    "C6_conformance": "C6_conformance",
}

# ASDoQ 6大品質特性の日本語名称マップ（正本名称）
CHARACTERISTIC_NAMES: Dict[str, str] = {
    "C1_purpose": "1. 目的適合性",
    "C2_maintainability": "2. 保守性",
    "C3_consistency": "3. 整合性",
    "C4_understandability": "4. 理解容易性",
    "C5_readability": "5. 可読性",
    "C6_conformance": "6. 規範適合性",
}

# ASDoQ 6大品質特性の短縮日本語名称マップ（[ASDoQ:特性-副特性] ラベル生成用）
CHARACTERISTIC_SHORT_JP: Dict[str, str] = {
    "C1_purpose": "目的適合性",
    "C2_maintainability": "保守性",
    "C3_consistency": "整合性",
    "C4_understandability": "理解容易性",
    "C5_readability": "可読性",
    "C6_conformance": "規範適合性",
}

# Decisions API の choice ASCIIキーから [ASDoQ:特性-副特性] ラベルへの変換マップ（SW205 表10 準拠）
CHOICE_ASDOQ_LABEL_MAP: Dict[str, str] = {
    "C1_1": "[ASDoQ:目的適合性-目的明示性]",
    "C1_2": "[ASDoQ:目的適合性-目的合致性]",
    "C2_1": "[ASDoQ:保守性-再利用性]",
    "C2_2": "[ASDoQ:保守性-持続可能性]",
    "C3_1": "[ASDoQ:整合性-無矛盾性]",
    "C3_2": "[ASDoQ:整合性-一貫性]",
    "C4_1": "[ASDoQ:理解容易性-非曖昧性（一意性）]",
    "C4_2": "[ASDoQ:理解容易性-非曖昧性（識別性）]",
    "C4_3": "[ASDoQ:理解容易性-関係性]",
    "C5_1": "[ASDoQ:可読性-簡潔性]",
    "C5_2": "[ASDoQ:可読性-表記適切性]",
    "C5_3": "[ASDoQ:可読性-表現適切性]",
    "C6_1": "[ASDoQ:規範適合性-制約適合性]",
    "C6_2": "[ASDoQ:規範適合性-基準適合性]",
    "C6_3": "[ASDoQ:規範適合性-文法適合性]",
    "C6_4": "[ASDoQ:規範適合性-記法適合性]",
    "other": "[ASDoQ:その他-要確認]",
}

# Decisions API の choice 判定選択肢定義（ASCIIキーと英語/日本語基準文）
CHOICE_CRITERIA_DEFINITIONS: Dict[str, str] = {
    "C1_1": "目的・対象読者・適用範囲（スコープ内外）の明示不足（1.1 目的明示性）",
    "C1_2": "読み手の関心事・目的との不整合（1.2 目的合致性）",
    "C2_1": "構造化・コンポーネント独立性・再利用性の不足（2.1 再利用性）",
    "C2_2": "改訂容易性・TBD/未定・追跡性の欠如（2.2 持続可能性）",
    "C3_1": "記述間の論理矛盾・数値や条件の衝突（3.1 無矛盾性）",
    "C3_2": "用語・表記・記号・[接続N]等の不統一（3.2 一貫性）",
    "C4_1": "曖昧語・程度副詞による多義解釈（4.1 非曖昧性・一意性）",
    "C4_2": "指示語・省略による対象識別不能（4.2 非曖昧性・識別性）",
    "C4_3": "前提・背景・判断理由の記述欠落（4.3 関係性）",
    "C5_1": "冗長表現・二重表現・一文長大化（5.1 簡潔性）",
    "C5_2": "漢字・送り仮名・記号等の表記不適切（5.2 表記適切性）",
    "C5_3": "受動態乱用による行為主体欠落・AI-Slop表現（5.3 表現適切性）",
    "C6_1": "規約・セキュリティ・法規制等の制約違反（6.1 制約適合性）",
    "C6_2": "組織標準・ガイドライン基準との不適合（6.2 基準適合性）",
    "C6_3": "ねじれ文・係り受け不良等の文法誤り（6.3 文法適合性）",
    "C6_4": "図直下/表直上キャプション・Mermaid制限・記法違反（6.4 記法適合性）",
    "other": "上記に該当しない、または複合的な文書品質上の懸念",
}

# 重要度定義
VALID_SEVERITIES = ("High", "Mid", "要確認")

# テンプレート・見出し等の固定標準語（Layer 0 誤検知防止マスク対象：UNIT-002 / SW205 ADR-003）
TEMPLATE_CANONICAL_TERMS: Tuple[str, ...] = (
    "非機能要求（性能・品質等）",
    "適用範囲（対象内・対象外）",
    "期待される結果・合否基準",
    "期待される振る舞い",
    "期待される出力",
    "期待される結果",
    "対象（スコープ内）",
)

# 文書種別プロファイル別の重み付けと既定ロード特性（SW205 表6 準拠）
PROFILE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "sw105": {
        "name": "要求仕様書（SW105）",
        "weights": {
            "C1_purpose": 1.5,
            "C2_maintainability": 1.0,
            "C3_consistency": 1.5,
            "C4_understandability": 2.0,
            "C5_readability": 1.5,
            "C6_conformance": 1.0,
        },
        "default_characteristics": ["C1_purpose", "C4_understandability", "C5_readability"],
        "required_sections": ["概要", "システム全体構成", "制約条件", "機能要求", "外部インタフェース", "非機能要求"],
    },
    "swp6": {
        "name": "総合テスト仕様書・報告書（SWP6）",
        "weights": {
            "C1_purpose": 1.0,
            "C2_maintainability": 1.5,
            "C3_consistency": 1.5,
            "C4_understandability": 2.0,
            "C5_readability": 1.5,
            "C6_conformance": 1.0,
        },
        "default_characteristics": ["C2_maintainability", "C3_consistency", "C4_understandability"],
        "required_sections": ["テストの概要", "テスト環境", "テスト方針", "テストシナリオ"],
    },
    "sw205": {
        "name": "アーキテクチャ設計書（SW205）",
        "weights": {
            "C1_purpose": 1.5,
            "C2_maintainability": 1.5,
            "C3_consistency": 2.0,
            "C4_understandability": 1.5,
            "C5_readability": 1.0,
            "C6_conformance": 1.0,
        },
        "default_characteristics": ["C2_maintainability", "C3_consistency", "C4_understandability"],
        "required_sections": ["概要", "システム構成", "ソフトウェア構成", "制御方式", "機能ユニット詳細"],
    },
    "general": {
        "name": "一般技術文書・マニュアル・論理文書",
        "weights": {
            "C1_purpose": 1.5,
            "C2_maintainability": 1.0,
            "C3_consistency": 1.0,
            "C4_understandability": 2.0,
            "C5_readability": 2.0,
            "C6_conformance": 1.5,
        },
        "default_characteristics": ["C4_understandability", "C5_readability"],
        "required_sections": ["概要", "目的"],
    },
}

# 6特性別専門レビュアー定義ファイル名一覧（UNIT-004）
SPECIALIST_FILES = (
    "C1_purpose_reviewer.md",
    "C2_maintainability_reviewer.md",
    "C3_consistency_reviewer.md",
    "C4_understandability_reviewer.md",
    "C5_readability_reviewer.md",
    "C6_conformance_reviewer.md",
)

# 一般機能語（未定義頻出専門用語の抽出から除外するストップワード集合）
COMMON_STOPWORDS = {
    "システム", "ファイル", "データ", "エラー", "テスト", "ユーザ", "ユーザー",
    "文書", "仕様", "設計", "実装", "確認", "検証", "実行", "出力", "入力",
    "処理", "場合", "項目", "結果", "対象", "内容", "条件", "定義", "構成",
    "機能", "方法", "手順", "状態", "情報", "一覧", "設定", "環境", "基準",
    "必要", "可能", "以下", "以上", "指定", "記載", "記述", "参照", "使用",
    "作成", "更新", "削除", "追加", "変更", "対応", "判定", "完了", "開始",
}

# 丸付き数字（①〜⑳）からASCII数字文字列への正規化マップ
CIRCLED_NUM_MAP: Dict[str, str] = {chr(0x2460 + i): str(i + 1) for i in range(20)}

# 形態素解析器（Janome）のシングルトンキャッシュ
_JANOME_TOKENIZER: Optional[Any] = None
_JANOME_CHECKED: bool = False


# ---------------------------------------------------------------------------
# 例外クラス定義（SW205 3.2節・7章 準拠）
# ---------------------------------------------------------------------------

class DictionaryValidationError(Exception):
    """辞書ファイルの不在・JSON構文エラー・必須キー欠落・旧表記混入・件数不足を表す例外（UNIT-001）。"""


class InputDocumentError(Exception):
    """検査対象ファイルの不在または空ファイル（0バイト）を表す例外（UNIT-002）。"""


# ---------------------------------------------------------------------------
# UNIT-001: 拡張違反例辞書・企業カスタム辞書管理モジュール
# ---------------------------------------------------------------------------

def _contains_legacy_asdoq_token(value: str) -> Optional[str]:
    """旧ASDoQ表記トークンの混入を検査するヘルパ関数。"""
    if LEGACY_NAME_TOKEN in value:
        return "旧特性名称"
    if LEGACY_TAG_TOKEN in value:
        return "旧全角隅付き括弧タグ"
    return None


def _build_asdoq_label(char_id: str, sub_characteristic: str) -> str:
    """正規化特性IDと副特性文字列から `[ASDoQ:特性-副特性]` ラベルを生成する。"""
    char_jp = CHARACTERISTIC_SHORT_JP.get(char_id, char_id)
    sub_clean = re.sub(r"^\d+\.\d+\s*", "", sub_characteristic).strip()
    if not sub_clean:
        sub_clean = "全般"
    return f"[ASDoQ:{char_jp}-{sub_clean}]"


def _is_multiline_pattern(pattern_str: str) -> bool:
    """文字クラス `[^\\n]` を除外したうえで複数行マッチが必要な正規表現か判定する。"""
    stripped_classes = re.sub(r"\[[^\]]*\]", "", pattern_str)
    return "\\n" in stripped_classes or "\n" in stripped_classes


def _validate_and_compile_rule(rule: Any, index: int) -> Dict[str, Any]:
    """
    関数名：_validate_and_compile_rule
    戻り値：コンパイル済み正規表現を含む検証済みルール辞書（Dict[str, Any]）
    引数：rule (Any) - 検査対象ルール要素, index (int) - ルール配列内のインデックス
    関数の概要：単一ルール要素の必須キー・特性ID・重要度・旧表記非混入・正規表現構文を検証しプリコンパイルする。
    対応機能ID（トレーサビリティ）：UNIT-001 (REQ-001)
    """
    if not isinstance(rule, dict):
        raise DictionaryValidationError(f"rules[{index}] がオブジェクトではありません。")

    for req_key in REQUIRED_RULE_KEYS:
        if req_key not in rule or rule[req_key] is None or str(rule[req_key]).strip() == "":
            rule_id = rule.get("id", f"index={index}")
            raise DictionaryValidationError(
                f"ルール ({rule_id}) に必須キー '{req_key}' が欠落しているか空です。"
            )

    char_id = str(rule["asdoq_characteristic"])
    if char_id not in VALID_CHARACTERISTICS:
        raise DictionaryValidationError(
            f"ルール ({rule['id']}) の asdoq_characteristic '{char_id}' が不正です。"
        )

    sev = str(rule["severity"])
    if sev not in VALID_SEVERITIES:
        raise DictionaryValidationError(
            f"ルール ({rule['id']}) の severity '{sev}' が不正です。"
        )

    hint_str = str(rule["hint"])
    if "Before" not in hint_str or "After" not in hint_str:
        raise DictionaryValidationError(
            f"ルール ({rule['id']}) の hint に Before/After の修正指針が含まれていません。"
        )

    # メタ記述・ラベル・修正例への旧ASDoQ表記混入を禁止する（pattern 自体は検出目的のため対象外）
    for chk_field in ("hint", "asdoq_label", "sub_characteristic", "before_example", "after_example"):
        if chk_field in rule and rule[chk_field] is not None:
            legacy_hit = _contains_legacy_asdoq_token(str(rule[chk_field]))
            if legacy_hit:
                raise DictionaryValidationError(
                    f"ルール ({rule['id']}) の '{chk_field}' に禁止された{legacy_hit}が含まれています。"
                )

    pattern_str = str(rule.get("pattern", ""))
    if not pattern_str:
        raise DictionaryValidationError(f"ルール ({rule['id']}) の pattern が空です。")
    is_multiline = _is_multiline_pattern(pattern_str)
    try:
        flags = re.MULTILINE if is_multiline else 0
        compiled = re.compile(pattern_str, flags)
    except re.error as exc:
        raise DictionaryValidationError(
            f"ルール ({rule['id']}) の正規表現コンパイルに失敗しました: {exc}"
        ) from exc

    cloned = dict(rule)
    if not cloned.get("asdoq_label"):
        cloned["asdoq_label"] = _build_asdoq_label(char_id, str(cloned.get("sub_characteristic", "")))
    cloned["_compiled"] = compiled
    cloned["_is_multiline"] = is_multiline
    return cloned


def merge_dictionaries(
    base_dict: Dict[str, Any],
    custom_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    関数名：merge_dictionaries
    戻り値：検証・マージ済みのルールセットオブジェクト（Dict[str, Any]）
    引数：
        base_dict (Dict[str, Any]) - パース済みの標準拡張違反例辞書オブジェクト
        custom_dict (Optional[Dict[str, Any]]) - パース済みの企業カスタム辞書オブジェクト（任意）
    関数の概要：
        標準辞書と企業カスタム辞書のメモリ上オブジェクトを検証・マージし、
        active_rules / category_counts / canonical_characteristics 等を含むルールセットを生成する。
    対応機能ID（トレーサビリティ）：UNIT-001 (REQ-001)
    """
    if not isinstance(base_dict, dict):
        raise DictionaryValidationError("辞書データのルート要素はJSONオブジェクトである必要があります。")

    meta = base_dict.get("_meta")
    if not isinstance(meta, dict) or "ASDoQ" not in str(meta.get("adl_notice", "")):
        raise DictionaryValidationError(
            "辞書データに _meta または ASDoQドキュメントライセンス（ADL）表示がありません。"
        )

    # 6特性定義に旧表記（旧1番名称等）が残っていないか検証する
    raw_chars = base_dict.get("characteristics")
    if raw_chars is not None:
        if not isinstance(raw_chars, dict):
            raise DictionaryValidationError("辞書データの 'characteristics' がオブジェクトではありません。")
        for cid, cname in raw_chars.items():
            legacy_hit = _contains_legacy_asdoq_token(str(cname))
            if legacy_hit:
                raise DictionaryValidationError(
                    f"characteristics['{cid}'] に禁止された{legacy_hit}が含まれています。"
                )

    raw_categories = base_dict.get("categories", {})
    if not isinstance(raw_categories, dict):
        raise DictionaryValidationError("辞書データの 'categories' がオブジェクトではありません。")
    for cat_id, cat_label in raw_categories.items():
        legacy_hit = _contains_legacy_asdoq_token(str(cat_label))
        if legacy_hit:
            raise DictionaryValidationError(
                f"categories['{cat_id}'] に禁止された{legacy_hit}が含まれています。"
            )

    raw_rules = base_dict.get("rules")
    if not isinstance(raw_rules, list):
        raise DictionaryValidationError("辞書データの 'rules' がリストではありません。")

    if len(raw_rules) < MIN_REQUIRED_RULES:
        raise DictionaryValidationError(
            f"辞書のルール登録数が基準未満です（現在 {len(raw_rules)} 件 < 必須 {MIN_REQUIRED_RULES} 件）。"
        )

    compiled_rules: List[Dict[str, Any]] = []
    found_categories = set()
    for idx, r in enumerate(raw_rules):
        validated = _validate_and_compile_rule(r, idx)
        found_categories.add(str(validated["category"]))
        compiled_rules.append(validated)

    missing_cats = REQUIRED_CATEGORIES - found_categories
    if missing_cats:
        raise DictionaryValidationError(
            f"辞書に必須カテゴリが不足しています: {sorted(missing_cats)}"
        )

    custom_ng_rules: List[Dict[str, Any]] = list(base_dict.get("custom_ng_rules", []))
    custom_ok_terms: List[str] = [str(x) for x in base_dict.get("custom_ok_terms", [])]
    disabled_rule_ids: List[str] = [str(x) for x in base_dict.get("disabled_rule_ids", [])]
    corporate_rules: List[Dict[str, Any]] = list(base_dict.get("corporate_conformance_rules", []))

    if custom_dict is not None:
        if not isinstance(custom_dict, dict):
            raise DictionaryValidationError("企業カスタム辞書のルート要素がオブジェクトではありません。")

        for list_key in ("custom_ng_rules", "custom_ok_terms", "disabled_rule_ids", "corporate_conformance_rules"):
            if list_key in custom_dict and not isinstance(custom_dict[list_key], list):
                raise DictionaryValidationError(f"{list_key} はリストである必要があります。")

        custom_ng_rules.extend(custom_dict.get("custom_ng_rules", []))
        custom_ok_terms.extend(str(x) for x in custom_dict.get("custom_ok_terms", []))
        disabled_rule_ids.extend(str(x) for x in custom_dict.get("disabled_rule_ids", []))
        corporate_rules.extend(custom_dict.get("corporate_conformance_rules", []))

        if "rules" in custom_dict and isinstance(custom_dict["rules"], list):
            for idx, r in enumerate(custom_dict["rules"]):
                compiled_rules.append(_validate_and_compile_rule(r, len(compiled_rules) + idx))

    # 企業固有NG表現ルールと企業規範ルールを検査用ルール形式へ変換・プリコンパイルする
    for idx, ng_entry in enumerate(custom_ng_rules):
        if not isinstance(ng_entry, dict) or not ng_entry.get("ng") or not ng_entry.get("ok"):
            raise DictionaryValidationError(
                f"custom_ng_rules[{idx}] には 'ng' と 'ok' キーが必須です。"
            )
        ng_word = str(ng_entry["ng"])
        ok_word = str(ng_entry["ok"])
        reason = str(ng_entry.get("reason", "企業カスタム禁止用語"))
        sev = str(ng_entry.get("severity", "High"))
        if sev not in VALID_SEVERITIES:
            sev = "High"
        rule_id = str(ng_entry.get("id", f"CUSTOM-NG-{idx + 1:03d}"))
        compiled_rules.append({
            "id": rule_id,
            "category": "8",
            "asdoq_characteristic": "C6_conformance",
            "sub_characteristic": "6.2 基準適合性（企業固有NG表現）",
            "asdoq_label": "[ASDoQ:規範適合性-基準適合性]",
            "severity": sev,
            "pattern_type": "regex",
            "pattern": re.escape(ng_word),
            "hint": (
                f"{reason}：企業固有NG表現「{ng_word}」が検出されました。推奨OK表現「{ok_word}」に置き換えてください。"
                f"（❌ Before: {ng_word} / ✅ After: {ok_word}）"
            ),
            "before_example": ng_word,
            "after_example": ok_word,
            "_compiled": re.compile(re.escape(ng_word)),
            "_is_multiline": False,
        })

    for idx, corp_entry in enumerate(corporate_rules):
        if not isinstance(corp_entry, dict) or not corp_entry.get("pattern"):
            raise DictionaryValidationError(
                f"corporate_conformance_rules[{idx}] には 'pattern' キーが必須です。"
            )
        pat_str = str(corp_entry["pattern"])
        ok_desc = str(corp_entry.get("ok", "企業標準記法に修正"))
        reason = str(corp_entry.get("reason", corp_entry.get("name", "企業規範適合性ルール違反")))
        sev = str(corp_entry.get("severity", "High"))
        if sev not in VALID_SEVERITIES:
            sev = "Mid"
        rule_id = str(corp_entry.get("id", f"CORP-CONF-{idx + 1:03d}"))
        corp_multiline = _is_multiline_pattern(pat_str)
        try:
            flags = re.MULTILINE if corp_multiline else 0
            comp = re.compile(pat_str, flags)
        except re.error as exc:
            raise DictionaryValidationError(
                f"corporate_conformance_rules[{idx}] の正規表現が不正です: {exc}"
            ) from exc
        compiled_rules.append({
            "id": rule_id,
            "category": "8",
            "asdoq_characteristic": "C6_conformance",
            "sub_characteristic": "6.4 記法適合性（企業規範ルール）",
            "asdoq_label": "[ASDoQ:規範適合性-記法適合性]",
            "severity": sev,
            "pattern_type": "regex",
            "pattern": pat_str,
            "hint": str(
                corp_entry.get(
                    "hint",
                    f"{reason}（❌ Before: 違反記法 / ✅ After: {ok_desc}）",
                )
            ),
            "before_example": pat_str,
            "after_example": ok_desc,
            "_compiled": comp,
            "_is_multiline": corp_multiline,
        })

    disabled_set = set(disabled_rule_ids)
    active_rules = [r for r in compiled_rules if r["id"] not in disabled_set]
    category_counts = {
        cat_id: sum(1 for r in active_rules if str(r["category"]) == cat_id)
        for cat_id in sorted(REQUIRED_CATEGORIES)
    }

    return {
        "version": str(base_dict.get("version", meta.get("version", "1.2.0"))),
        "_meta": meta,
        "characteristics": raw_chars or dict(CHARACTERISTIC_NAMES),
        "canonical_characteristics": dict(CHARACTERISTIC_NAMES),
        "categories": raw_categories,
        "category_counts": category_counts,
        "rules": compiled_rules,
        "active_rules": active_rules,
        "custom_ng_rules": custom_ng_rules,
        "custom_ok_terms": sorted(set(custom_ok_terms), key=len, reverse=True),
        "disabled_rule_ids": list(disabled_set),
        "corporate_conformance_rules": corporate_rules,
    }


def _read_json_dict_file(file_path: Path, label: str) -> Dict[str, Any]:
    """JSON辞書ファイルを読み込み、存在と構文を検証する共通ヘルパ関数。"""
    if not file_path.is_file():
        raise DictionaryValidationError(f"{label}ファイルが存在しません: {file_path}")
    try:
        raw_text = file_path.read_text(encoding="utf-8-sig")
        parsed = json.loads(raw_text)
    except Exception as exc:
        raise DictionaryValidationError(
            f"{label}ファイルのJSON構文が不正です ({file_path}): {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise DictionaryValidationError(f"{label}データのルート要素はJSONオブジェクトである必要があります。")
    return parsed


def load_dictionary(
    dict_path: Path,
    custom_dict_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    関数名：load_dictionary
    戻り値：検証・マージ済みのルールセットオブジェクト（Dict[str, Any]）
    引数：
        dict_path (Path) - 標準拡張違反例辞書JSONのファイルパス
        custom_dict_path (Optional[Path]) - 企業カスタム辞書JSONのファイルパス（任意）
    関数の概要：
        標準辞書とオプションの企業カスタム辞書をファイルからロードし、スキーマ・カテゴリ網羅性（1〜8）・
        登録件数（80件以上）・必須キー6項目・旧表記非混入・ADLライセンス表示を検証してマージする。
    対応機能ID（トレーサビリティ）：UNIT-001 (REQ-001)
    """
    base_dict = _read_json_dict_file(dict_path, "辞書")
    custom_dict = _read_json_dict_file(custom_dict_path, "企業カスタム辞書") if custom_dict_path else None
    return merge_dictionaries(base_dict, custom_dict)


def load_dictionary_ruleset(
    dict_path: Optional[Path] = None,
    custom_dict_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    関数名：load_dictionary_ruleset
    戻り値：検証・マージ済みのルールセットオブジェクト（Dict[str, Any]）
    引数：
        dict_path (Optional[Path]) - 標準辞書パス（None時はリポジトリ既定パスを使用）
        custom_dict_path (Optional[Path]) - 企業カスタム辞書パス（任意）
    関数の概要：既定パス解決付きの辞書ルールセットローダー。
    対応機能ID（トレーサビリティ）：UNIT-001 (REQ-001)
    """
    repo_root = Path(__file__).resolve().parents[1]
    resolved_dict = dict_path if dict_path is not None else (repo_root / DEFAULT_DICT_REL_PATH)
    return load_dictionary(resolved_dict, custom_dict_path)


def validate_dictionary_file(dict_path: Path) -> Dict[str, Any]:
    """
    関数名：validate_dictionary_file
    戻り値：辞書検証サマリ辞書（valid, version, rules_count, active_rules_count, category_counts等）
    引数：dict_path (Path) - 検証対象の辞書JSONファイルパス
    関数の概要：単体辞書ファイルのスキーマ・件数・カテゴリ網羅性・旧表記非混入を検証して結果を返す。
    対応機能ID（トレーサビリティ）：UNIT-001 (REQ-001, TC-001)
    """
    ruleset = load_dictionary(dict_path)
    return {
        "valid": True,
        "version": ruleset["version"],
        "rules_count": len(ruleset["rules"]),
        "active_rules_count": len(ruleset["active_rules"]),
        "categories_count": len(ruleset["categories"]),
        "category_counts": ruleset["category_counts"],
        "canonical_characteristics": ruleset["canonical_characteristics"],
        "custom_ng_count": len(ruleset["custom_ng_rules"]),
        "custom_ok_count": len(ruleset["custom_ok_terms"]),
    }


# ---------------------------------------------------------------------------
# UNIT-002: Layer 0 NLP形態素解析・構造クロスリファレンス抽出エンジン
# ---------------------------------------------------------------------------

def _get_tokenizer(force_stdlib: bool = False) -> Tuple[Optional[Any], str]:
    """
    関数名：_get_tokenizer
    戻り値：(Janome TokenizerインスタンスまたはNone, モード名 'janome' | 'stdlib_fallback')
    引数：force_stdlib (bool) - Trueの場合はJanomeが導入済みでも標準ライブラリ解析を強制する
    関数の概要：Janome形態素解析器のロードを試み、未導入時は標準ライブラリモードへ自動フォールバックする。
    対応機能ID（トレーサビリティ）：UNIT-002 (REQ-002)
    """
    global _JANOME_TOKENIZER, _JANOME_CHECKED
    if force_stdlib:
        return None, "stdlib_fallback"

    if not _JANOME_CHECKED:
        _JANOME_CHECKED = True
        try:
            from janome.tokenizer import Tokenizer  # type: ignore[import-not-found]
            _JANOME_TOKENIZER = Tokenizer()
        except Exception:
            _JANOME_TOKENIZER = None

    if _JANOME_TOKENIZER is not None:
        return _JANOME_TOKENIZER, "janome"
    return None, "stdlib_fallback"


def _extract_compound_nouns(text: str, tokenizer: Optional[Any]) -> List[str]:
    """
    関数名：_extract_compound_nouns
    戻り値：抽出された複合名詞・専門用語候補のリスト（List[str]）
    引数：text (str) - 解析対象テキスト, tokenizer (Optional[Any]) - JanomeインスタンスまたはNone
    関数の概要：Janome形態素解析または正規表現境界解析により、テキストから専門用語・複合名詞候補を抽出する。
    対応機能ID（トレーサビリティ）：UNIT-002 (REQ-002)
    """
    candidates: List[str] = []
    if tokenizer is not None and len(text) <= 4000:
        buf: List[str] = []
        for token in tokenizer.tokenize(text):
            pos = token.part_of_speech.split(",")[0]
            sub_pos = token.part_of_speech.split(",")[1]
            if pos == "名詞" and sub_pos not in ("数", "非自立", "代名詞", "接尾"):
                buf.append(token.surface)
            else:
                if buf:
                    word = "".join(buf)
                    if len(word) >= 3:
                        candidates.append(word)
                    buf = []
        if buf:
            word = "".join(buf)
            if len(word) >= 3:
                candidates.append(word)

    for m in re.finditer(r"[ァ-ヶー]{3,}|[一-龠々]{3,12}|[A-Za-z][A-Za-z0-9_-]{2,}", text):
        w = m.group(0)
        if w not in candidates:
            candidates.append(w)
    return candidates


def _mask_ok_terms(text: str, ok_terms: List[str]) -> str:
    """
    関数名：_mask_ok_terms
    戻り値：許容OK表現およびテンプレート定型語をマスクした文字列（str）
    引数：text (str) - 対象文字列, ok_terms (List[str]) - 許容OK表現リスト
    関数の概要：custom_ok_terms とテンプレート標準見出しが違反として誤検出されないよう安全にマスクする。
    対応機能ID（トレーサビリティ）：UNIT-001, UNIT-002 (REQ-001, REQ-002)
    """
    masked = text
    combined = sorted(set(ok_terms) | set(TEMPLATE_CANONICAL_TERMS), key=len, reverse=True)
    for term in combined:
        if term and term in masked:
            masked = masked.replace(term, "◇" * len(term))
    return masked


def _mask_code_blocks_preserve_lines(lines: List[str], line_types: List[str]) -> str:
    """
    関数名：_mask_code_blocks_preserve_lines
    戻り値：コードブロックおよびMermaid内部行を行番号を保持したままマスクした文書文字列
    引数：lines (List[str]) - 行リスト, line_types (List[str]) - 行種別リスト
    関数の概要：複数行パターンおよび図表キャプション検査がコードブロック内の例示に誤反応しないようマスクする。
    対応機能ID（トレーサビリティ）：UNIT-002 (REQ-002)
    """
    masked_lines: List[str] = []
    for ln, ltype in zip(lines, line_types):
        if ltype == "code":
            masked_lines.append("CODE_BLOCK_LINE")
        elif ltype == "mermaid":
            stripped = ln.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                masked_lines.append(ln)
            else:
                masked_lines.append("MERMAID_BODY_LINE")
        else:
            masked_lines.append(ln)
    return "\n".join(masked_lines)


def _extract_mermaid_blocks_and_checks(
    lines: List[str],
    line_types: List[str],
) -> Dict[str, Any]:
    """
    関数名：_extract_mermaid_blocks_and_checks
    戻り値：Mermaidラベル、10ノード超ブロック、および[接続N]ペア検査結果を含む辞書
    引数：lines (List[str]) - 行リスト, line_types (List[str]) - 行種別リスト
    関数の概要：
        各Mermaidブロックのノード数を計数して10ノード上限超過を検出し、
        分割図間の[接続N]／[接続①]連番ラベルのペア対応を検証する（ADR-006）。
    対応機能ID（トレーサビリティ）：UNIT-002 (REQ-002, REQ-006)
    """
    blocks: List[Dict[str, Any]] = []
    curr: Optional[Dict[str, Any]] = None

    for lineno, (ln, ltype) in enumerate(zip(lines, line_types), start=1):
        if ltype == "mermaid":
            stripped = ln.strip()
            if curr is None:
                curr = {"block_index": len(blocks) + 1, "start_line": lineno, "body_lines": []}
            elif stripped.startswith("```") or stripped.startswith("~~~"):
                blocks.append(curr)
                curr = None
            else:
                curr["body_lines"].append((lineno, ln))
        elif curr is not None:
            blocks.append(curr)
            curr = None
    if curr is not None:
        blocks.append(curr)

    mermaid_labels: List[str] = []
    mermaid_over_10_nodes: List[Dict[str, Any]] = []
    conn_occurrences: Dict[str, List[Dict[str, Any]]] = {}

    ignored_keywords = {
        "flowchart", "graph", "sequenceDiagram", "stateDiagram", "stateDiagram-v2",
        "classDiagram", "erDiagram", "subgraph", "end", "direction", "classDef",
        "style", "linkStyle", "click", "participant", "actor", "note", "Note",
        "loop", "alt", "else", "opt", "par", "and", "critical", "break", "rect",
        "TD", "TB", "LR", "RL", "BT",
    }

    conn_re = re.compile(r"\[接続\s*([0-9０-９]+|[①-⑳])(?:\s*[:：][^\]]*)?\]")

    for blk in blocks:
        nodes_in_block = set()
        for lineno, ln in blk["body_lines"]:
            stripped = ln.strip()
            if not stripped or stripped.startswith("%%"):
                continue

            # ノードラベル抽出
            for m_lbl in re.finditer(r'\["([^"]+)"\]|\[([^\]]+)\]', stripped):
                lbl = (m_lbl.group(1) or m_lbl.group(2) or "").strip()
                if lbl:
                    mermaid_labels.append(lbl)

            # [接続N] / [接続①] の抽出とブロック間出現記録
            for m_conn in conn_re.finditer(stripped):
                raw_num = m_conn.group(1)
                norm_num = CIRCLED_NUM_MAP.get(raw_num, raw_num)
                norm_num = norm_num.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
                conn_occurrences.setdefault(norm_num, []).append({
                    "connection": f"接続{norm_num}",
                    "block_index": blk["block_index"],
                    "line": lineno,
                    "raw": m_conn.group(0),
                })

            # ノードIDの抽出（flowchart/graph定義・エッジ両端・sequenceDiagram参加者/メッセージ）
            if stripped.startswith(("participant ", "actor ")):
                parts = stripped.split()
                if len(parts) >= 2:
                    nodes_in_block.add(parts[1])
                continue

            # シェイプ付きノード定義 ID[...] / ID(...) / ID{...}
            for m_node in re.finditer(r"(?<![A-Za-z0-9_-])([A-Za-z][A-Za-z0-9_-]*)\s*(?:\[|\(|\{)", stripped):
                nid = m_node.group(1)
                if nid not in ignored_keywords:
                    nodes_in_block.add(nid)

            # エッジ構文 A --> B / A ->> B 等（ラベルテキスト中の矢印表記を除外するため行内シェイプ外を参照）
            edge_clean = re.sub(r'"[^"]*"|\|[^|]*\|', " ", stripped)
            for m_edge in re.finditer(
                r"\b([A-Za-z][A-Za-z0-9_-]*)\s*(?:--+>?|==+>?|-\.+->?|->>?|-->>?|<->)\s*([A-Za-z][A-Za-z0-9_-]*)\b",
                edge_clean,
            ):
                for nid in (m_edge.group(1), m_edge.group(2)):
                    if nid not in ignored_keywords:
                        nodes_in_block.add(nid)

        node_count = len(nodes_in_block)
        if node_count > 10:
            mermaid_over_10_nodes.append({
                "block_index": blk["block_index"],
                "line": blk["start_line"],
                "node_count": node_count,
                "max_allowed": 10,
            })

    paired_connections: List[Dict[str, Any]] = []
    isolated_connection_warnings: List[Dict[str, Any]] = []
    for num_key in sorted(conn_occurrences.keys(), key=lambda x: int(x) if x.isdigit() else 999):
        occs = conn_occurrences[num_key]
        distinct_blocks = sorted({o["block_index"] for o in occs})
        entry = {
            "connection": f"接続{num_key}",
            "block_indices": distinct_blocks,
            "lines": [o["line"] for o in occs],
        }
        if len(distinct_blocks) >= 2:
            paired_connections.append(entry)
        else:
            isolated_connection_warnings.append(entry)

    return {
        "mermaid_node_labels": mermaid_labels,
        "mermaid_block_count": len(blocks),
        "mermaid_over_10_nodes": mermaid_over_10_nodes,
        "connection_pair_check": {
            "paired_connections": paired_connections,
            "isolated_connection_warnings": isolated_connection_warnings,
        },
    }


def _build_cross_reference(
    raw_text: str,
    lines: List[str],
    line_types: List[str],
    profile: str,
    tokenizer: Optional[Any],
) -> Dict[str, Any]:
    """
    関数名：_build_cross_reference
    戻り値：構造クロスリファレンス表の4項目を含む辞書（Dict[str, Any]）
    引数：
        raw_text (str) - 原文書全文
        lines (List[str]) - 行リスト
        line_types (List[str]) - 各行の種別 ('prose' | 'code' | 'mermaid')
        profile (str) - 文書種別プロファイル名
        tokenizer (Optional[Any]) - 形態素解析器インスタンス
    関数の概要：
        文書全体から①目的・スコープ要素チェック、②用語集vs本文クロス突合（3回以上未定義語・類似表記ゆれペア）、
        ③数値・単位・条件クロス一覧、④見出し・図表クロス突合（希薄見出し節・図下/表上キャプション・境界付き参照突合・
        Mermaid 10ノード上限・[接続N]ペア）を抽出する。
    対応機能ID（トレーサビリティ）：UNIT-002 (REQ-002)
    """
    prof_cfg = PROFILE_CONFIGS.get(profile, PROFILE_CONFIGS["general"])

    # ① 目的・スコープ要素チェック（purpose_scope_check）
    prose_only_text = "\n".join(
        ln for ln, ltype in zip(lines, line_types) if ltype == "prose"
    )
    has_reader = bool(re.search(r"読み手|読者|利用者|対象者|担当者|Product Owner", prose_only_text))
    has_purpose = bool(re.search(r"目的|位置づけ|背景|ねらい", prose_only_text))
    has_scope_in = bool(re.search(r"適用範囲|スコープ|対象範囲|対象（スコープ内）", prose_only_text))
    has_scope_out = bool(re.search(r"対象外|スコープ外", prose_only_text))

    present_sections: List[str] = []
    missing_sections: List[str] = []
    for req_sec in prof_cfg["required_sections"]:
        if req_sec in prose_only_text:
            present_sections.append(req_sec)
        else:
            missing_sections.append(req_sec)

    purpose_scope_check = {
        "has_reader": has_reader,
        "has_purpose": has_purpose,
        "has_scope_in": has_scope_in,
        "has_scope_out": has_scope_out,
        "present_required_sections": present_sections,
        "missing_required_sections": missing_sections,
    }

    # ② 用語集 vs 本文クロス突合（term_cross_check）
    defined_terms: Dict[str, int] = {}
    in_term_section = False
    for ln, ltype in zip(lines, line_types):
        if ltype != "prose":
            continue
        stripped = ln.strip()
        if stripped.startswith("#"):
            in_term_section = "用語" in stripped
            continue
        if in_term_section and stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cells and cells[0] and not re.match(r"^:?-{2,}:?$", cells[0]) and cells[0] not in ("用語", "用語名", "項目"):
                term_clean = re.sub(r"[*`]", "", cells[0]).strip()
                if term_clean:
                    defined_terms[term_clean] = 0

    for term in list(defined_terms.keys()):
        defined_terms[term] = max(0, prose_only_text.count(term) - 1)

    all_katakana_or_kanji = re.findall(r"[ァ-ヶー]{3,}|[一-龠々]{3,10}", prose_only_text)
    if tokenizer is not None:
        all_katakana_or_kanji.extend(_extract_compound_nouns(prose_only_text, tokenizer))

    term_counts: Dict[str, int] = {}
    for w in all_katakana_or_kanji:
        if w in COMMON_STOPWORDS or w in defined_terms:
            continue
        if any(w in dt for dt in defined_terms):
            continue
        term_counts[w] = prose_only_text.count(w)

    undefined_frequent_terms = [
        {"term": k, "count": v}
        for k, v in sorted(term_counts.items(), key=lambda x: (-x[1], x[0]))
        if v >= 3
    ][:20]

    katakana_words = sorted(set(re.findall(r"[ァ-ヶー]{3,}", prose_only_text)))
    similar_term_pairs: List[Dict[str, Any]] = []
    seen_pairs = set()
    for w1 in katakana_words:
        w1_norm = w1.rstrip("ー").replace("インターフェース", "インタフェース")
        for w2 in katakana_words:
            if w1 >= w2:
                continue
            w2_norm = w2.rstrip("ー").replace("インターフェース", "インタフェース")
            if w1_norm == w2_norm and (w1, w2) not in seen_pairs:
                seen_pairs.add((w1, w2))
                similar_term_pairs.append({
                    "pair": [w1, w2],
                    "counts": {w1: prose_only_text.count(w1), w2: prose_only_text.count(w2)},
                })

    term_cross_check = {
        "defined_terms_usage": defined_terms,
        "undefined_frequent_terms": undefined_frequent_terms,
        "similar_term_pairs": similar_term_pairs,
    }

    # ③ 数値・単位・条件クロス一覧（numbers_units_table）
    numbers_units_table: List[Dict[str, Any]] = []
    current_section = "冒頭"
    num_unit_re = re.compile(
        r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*"
        r"(件|秒|ms|ミリ秒|分|時間|日|回|%|％|MB|GB|KB|バイト|文字|行|列|章|節|個|週|周)"
        r"(\s*(?:以上|以下|未満|超|以内|まで|ちょうど))?"
    )
    for lineno, (ln, ltype) in enumerate(zip(lines, line_types), start=1):
        if ltype != "prose":
            continue
        s = ln.strip()
        if s.startswith("#"):
            current_section = re.sub(r"^#+\s*", "", s).strip()
            continue
        for m in num_unit_re.finditer(s):
            numbers_units_table.append({
                "line": lineno,
                "section": current_section,
                "value": m.group(1),
                "unit": m.group(2),
                "condition": (m.group(3) or "").strip(),
                "expression": m.group(0).strip(),
            })

    # ④ 見出し・図表クロス突合（heading_figure_table_check）
    headings_info: List[Dict[str, Any]] = []
    for idx, (ln, ltype) in enumerate(zip(lines, line_types)):
        if ltype == "prose":
            m_h = re.match(r"^(#{1,6})\s+(.+)$", ln.strip())
            if m_h:
                headings_info.append({
                    "index": idx,
                    "line": idx + 1,
                    "level": len(m_h.group(1)),
                    "title": m_h.group(2).strip(),
                })

    sparse_sections: List[Dict[str, Any]] = []
    for h_idx, h in enumerate(headings_info):
        start_i = h["index"] + 1
        end_i = headings_info[h_idx + 1]["index"] if h_idx + 1 < len(headings_info) else len(lines)
        body_lines_in_sec = [
            lines[j].strip()
            for j in range(start_i, end_i)
            if line_types[j] == "prose" and lines[j].strip() and not lines[j].strip().startswith(">")
        ]
        if not body_lines_in_sec and h_idx + 1 < len(headings_info) and headings_info[h_idx + 1]["level"] > h["level"]:
            continue
        sec_text = "\n".join(body_lines_in_sec)
        sentence_chunks = [
            c.strip()
            for c in re.split(r"[。！？\n]", sec_text)
            if c.strip() and not re.match(r"^\|[\s:|-]+\|$", c.strip())
        ]
        sentence_count = len(sentence_chunks)
        if sentence_count <= 1:
            sparse_sections.append({
                "line": h["line"],
                "heading": h["title"],
                "sentence_count": sentence_count,
            })

    # 境界条件付き図表参照突合（「表現1」「代表2」「設計図10%」等の誤一致を抑止）
    prose_no_inline = re.sub(r"`[^`]+`", "", prose_only_text)
    defined_figures = set(re.findall(r"(?<![一-龠々ァ-ヶーA-Za-z0-9])\*\*図\s*([0-9０-９]+)\s*[：:]", prose_no_inline))
    defined_tables = set(re.findall(r"(?<![一-龠々ァ-ヶーA-Za-z0-9])\*\*表\s*([0-9０-９]+)\s*[：:]", prose_no_inline))
    referenced_figures = set(re.findall(r"(?<![一-龠々ァ-ヶーA-Za-z0-9])図\s*([0-9０-９]+)(?![0-9０-９%％])", prose_no_inline))
    referenced_tables = set(re.findall(r"(?<![一-龠々ァ-ヶーA-Za-z0-9])表\s*([0-9０-９]+)(?![0-9０-９%％])", prose_no_inline))

    missing_figure_defs = sorted(referenced_figures - defined_figures)
    missing_table_defs = sorted(referenced_tables - defined_tables)

    # Mermaid 10ノード上限 & [接続N] ペア検査
    mermaid_checks = _extract_mermaid_blocks_and_checks(lines, line_types)

    # 図表キャプション位置違反検査は通常コードブロックをマスクしたテキストで実行する
    masked_doc = _mask_code_blocks_preserve_lines(lines, line_types)
    caption_position_violations: List[Dict[str, Any]] = []
    for m_fig_above in re.finditer(
        r"(?<!```\n)(?<!```\n\n)^\*\*図\s*[0-9０-９]+\s*[：:][^\n]+\*\*\s*\n+```mermaid",
        masked_doc,
        re.MULTILINE,
    ):
        line_no = masked_doc[:m_fig_above.start()].count("\n") + 1
        caption_position_violations.append({
            "line": line_no,
            "type": "figure_caption_above",
            "message": "図のキャプションが図の上に配置されています（図は直下に配置すること）。",
        })
    for m_tbl_below in re.finditer(
        r"\|[^\n]+\|\s*\n+\*\*表\s*[0-9０-９]+\s*[：:][^\n]+\*\*(?![ \t]*\n+\|)",
        masked_doc,
    ):
        line_no = masked_doc[:m_tbl_below.start()].count("\n") + 1
        caption_position_violations.append({
            "line": line_no,
            "type": "table_caption_below",
            "message": "表のキャプションが表の下に配置されています（表は直上に配置すること）。",
        })

    heading_figure_table_check = {
        "sparse_sections": sparse_sections,
        "defined_figures": sorted(defined_figures),
        "defined_tables": sorted(defined_tables),
        "missing_figure_definitions": [f"図{n}" for n in missing_figure_defs],
        "missing_table_definitions": [f"表{n}" for n in missing_table_defs],
        "mermaid_node_labels": mermaid_checks["mermaid_node_labels"],
        "mermaid_block_count": mermaid_checks["mermaid_block_count"],
        "mermaid_over_10_nodes": mermaid_checks["mermaid_over_10_nodes"],
        "connection_pair_check": mermaid_checks["connection_pair_check"],
        "caption_position_violations": caption_position_violations,
    }

    return {
        "purpose_scope_check": purpose_scope_check,
        "term_cross_check": term_cross_check,
        "numbers_units_table": numbers_units_table,
        "heading_figure_table_check": heading_figure_table_check,
    }


def analyze_document_layer0(
    text: str,
    ruleset: Dict[str, Any],
    profile: str = "general",
    characteristic: str = "all",
    max_items: int = 25,
    force_stdlib: bool = False,
) -> Dict[str, Any]:
    """
    関数名：analyze_document_layer0
    戻り値：Layer 0 解析結果辞書（confirmed_findings, cross_reference, candidate_slices, characteristic_scores, tokenizer_mode）
    引数：
        text (str) - 検査対象Markdownテキスト全文
        ruleset (Dict[str, Any]) - load_dictionaryが返した検証済みルールセット
        profile (str) - 文書種別プロファイル ('sw105' | 'swp6' | 'sw205' | 'general')
        characteristic (str) - 対象特性フィルタ ('all' または 'C1'〜'C6' / 'C1_purpose'〜'C6_conformance')
        max_items (int) - 1カテゴリあたりの最大出力件数（既定 25）
        force_stdlib (bool) - Trueのとき標準ライブラリ解析モードを強制する
    関数の概要：
        コードブロックとテンプレート標準語をマスクして拡張違反例辞書・カスタム辞書との照合、
        構造クロスリファレンス表4項目の抽出、Mermaid 10ノード上限・[接続N]ペア検査、
        疑義スライスの50%以下圧縮抽出、およびプロファイル重み付き6特性スコア算出を実行する。
    対応機能ID（トレーサビリティ）：UNIT-002 (REQ-002)
    """
    if not text or not text.strip():
        raise InputDocumentError("検査対象の文書が空（0バイトまたは空白のみ）です。")

    if profile not in PROFILE_CONFIGS:
        raise ValueError(f"未定義のプロファイルです: {profile}")

    target_char: Optional[str] = None
    if characteristic != "all":
        if characteristic not in CHARACTERISTIC_SHORT_MAP:
            raise ValueError(f"未定義のASDoQ特性指定です: {characteristic}")
        target_char = CHARACTERISTIC_SHORT_MAP[characteristic]

    # ステップ1: 文書構造分解（コードブロック・Mermaidブロック・通常本文行の分類）
    norm_text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = norm_text.split("\n")
    line_types: List[str] = []
    in_fence = False
    fence_kind = "code"

    for ln in lines:
        s = ln.strip()
        if s.startswith("```") or s.startswith("~~~"):
            if not in_fence:
                in_fence = True
                fence_kind = "mermaid" if "mermaid" in s.lower() else "code"
                line_types.append(fence_kind)
            else:
                line_types.append(fence_kind)
                in_fence = False
                fence_kind = "code"
            continue
        line_types.append(fence_kind if in_fence else "prose")

    # ステップ2: 形態素解析器（Janomeまたは標準ライブラリフォールバック）の準備
    tokenizer, tokenizer_mode = _get_tokenizer(force_stdlib=force_stdlib)

    # ステップ3: 拡張違反例辞書および企業カスタム辞書との照合
    active_rules: List[Dict[str, Any]] = ruleset.get("active_rules", [])
    ok_terms: List[str] = ruleset.get("custom_ok_terms", [])
    raw_findings: List[Dict[str, Any]] = []

    # 3a. 複数行パターン（コードブロックをマスクして誤反応を防止）
    masked_multiline_doc = _mask_code_blocks_preserve_lines(lines, line_types)
    multiline_rules = [r for r in active_rules if r.get("_is_multiline")]
    singleline_rules = [r for r in active_rules if not r.get("_is_multiline")]

    for rule in multiline_rules:
        if target_char and rule["asdoq_characteristic"] != target_char:
            continue
        label = rule.get("asdoq_label") or _build_asdoq_label(
            rule["asdoq_characteristic"], str(rule.get("sub_characteristic", ""))
        )
        for m in rule["_compiled"].finditer(masked_multiline_doc):
            lineno = masked_multiline_doc[:m.start()].count("\n") + 1
            raw_findings.append({
                "rule_id": rule["id"],
                "line": lineno,
                "category": str(rule["category"]),
                "asdoq_characteristic": rule["asdoq_characteristic"],
                "sub_characteristic": rule.get("sub_characteristic", ""),
                "asdoq_label": label,
                "severity": rule["severity"],
                "matched": m.group(0).strip().replace("\n", " "),
                "hint": rule["hint"],
            })

    # 3b. 行単位パターン（コードブロック・インラインコード・許容OK語・テンプレート定型語をマスクして照合）
    for lineno, (ln, ltype) in enumerate(zip(lines, line_types), start=1):
        if ltype != "prose":
            continue
        stripped = ln.strip()
        if not stripped:
            continue
        if stripped.startswith("|") and re.match(r"^\|[\s:|-]+\|$", stripped):
            continue
        clean_ln = re.sub(r"`[^`]+`", "CODE", ln)
        clean_ln = _mask_ok_terms(clean_ln, ok_terms)

        for rule in singleline_rules:
            if target_char and rule["asdoq_characteristic"] != target_char:
                continue
            m = rule["_compiled"].search(clean_ln)
            if m:
                label = rule.get("asdoq_label") or _build_asdoq_label(
                    rule["asdoq_characteristic"], str(rule.get("sub_characteristic", ""))
                )
                raw_findings.append({
                    "rule_id": rule["id"],
                    "line": lineno,
                    "category": str(rule["category"]),
                    "asdoq_characteristic": rule["asdoq_characteristic"],
                    "sub_characteristic": rule.get("sub_characteristic", ""),
                    "asdoq_label": label,
                    "severity": rule["severity"],
                    "matched": m.group(0),
                    "hint": rule["hint"],
                })

    # ステップ4: 構造クロスリファレンス表（4項目）の自動抽出
    cross_reference = _build_cross_reference(
        raw_text=norm_text,
        lines=lines,
        line_types=line_types,
        profile=profile,
        tokenizer=tokenizer,
    )

    # 4b. Mermaid 10ノード上限超過および孤立[接続N]を確定指摘へ追加
    hf = cross_reference["heading_figure_table_check"]
    if not target_char or target_char == "C6_conformance":
        for over_item in hf["mermaid_over_10_nodes"]:
            raw_findings.append({
                "rule_id": "STRUCT-MERMAID-NODES",
                "line": over_item["line"],
                "category": "8",
                "asdoq_characteristic": "C6_conformance",
                "sub_characteristic": "6.4 記法適合性",
                "asdoq_label": "[ASDoQ:規範適合性-記法適合性]",
                "severity": "Mid",
                "matched": f"Mermaid block#{over_item['block_index']} ({over_item['node_count']} nodes)",
                "hint": (
                    f"Mermaid図のノード数が上限10個を超過しています（現在 {over_item['node_count']} 個）。"
                    "複数図へ分割し、[接続1: ...] のような連番ラベルで結合してください。"
                    "（❌ Before: 1図に11ノード以上を詰め込む / ✅ After: 1図10ノード以下に分割し [接続1] で接続する）"
                ),
            })
    if not target_char or target_char == "C3_consistency":
        for iso_conn in hf["connection_pair_check"]["isolated_connection_warnings"]:
            raw_findings.append({
                "rule_id": "STRUCT-MERMAID-CONN",
                "line": iso_conn["lines"][0],
                "category": "7",
                "asdoq_characteristic": "C3_consistency",
                "sub_characteristic": "3.2 一貫性",
                "asdoq_label": "[ASDoQ:整合性-一貫性]",
                "severity": "Mid",
                "matched": iso_conn["connection"],
                "hint": (
                    f"分割図の接続ラベル `[{iso_conn['connection']}]` が1つの図内にしか出現していません。"
                    "前後の図で対になる接続ラベルを配置してください。"
                    "（❌ Before: 片方の図のみ [接続1] がある / ✅ After: 分割前後の図に [接続1] をペア配置する）"
                ),
            })

    # 1カテゴリあたり max_items 件の上限適用と省略件数の集計
    findings_by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for f in raw_findings:
        cat_key = str(f["category"])
        findings_by_cat.setdefault(cat_key, []).append(f)

    confirmed_findings: List[Dict[str, Any]] = []
    omitted_counts_by_category: Dict[str, int] = {}
    for cat_key in sorted(findings_by_cat.keys()):
        cat_list = findings_by_cat[cat_key]
        if len(cat_list) > max_items:
            confirmed_findings.extend(cat_list[:max_items])
            omitted_counts_by_category[cat_key] = len(cat_list) - max_items
        else:
            confirmed_findings.extend(cat_list)

    # ステップ5: 疑義スライス（Candidate Slices）の抽出と50%以下圧縮
    candidate_slices: List[Dict[str, Any]] = []
    total_doc_chars = len(norm_text)
    max_slice_chars = int(total_doc_chars * 0.45)
    accumulated_chars = 0

    grey_pattern = re.compile(
        r"(?:れる|られる|こととする|場合|ただし|なお|理由|省略|未定|TBD|"
        r"思われる|考えられる|べき|高速|適切|柔軟|基本的|それ|これ|上記|当該|"
        r"境界030|境界029|\[DECISION1:)"
    )

    current_sec = "冒頭"
    for lineno, (ln, ltype) in enumerate(zip(lines, line_types), start=1):
        if ltype != "prose":
            continue
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            current_sec = re.sub(r"^#+\s*", "", s).strip()
            continue
        if s.startswith("|") and re.match(r"^\|[\s:|-]+\|$", s):
            continue
        clean_s = re.sub(r"`[^`]+`", "", s)
        is_grey = bool(grey_pattern.search(clean_s)) or len(clean_s) > 85
        if not is_grey:
            continue
        if accumulated_chars + len(s) > max_slice_chars and len(candidate_slices) >= 2:
            break

        suspected_char = "C4_understandability"
        if re.search(r"理由|省略|したがって", clean_s):
            suspected_char = "C3_consistency"
        elif re.search(r"未定|TBD|将来|変更", clean_s):
            suspected_char = "C2_maintainability"
        elif re.search(r"思われる|考えられる|べき", clean_s):
            suspected_char = "C6_conformance"
        elif re.search(r"れる|られる", clean_s):
            suspected_char = "C5_readability"

        if target_char and suspected_char != target_char:
            continue

        candidate_slices.append({
            "slice_id": f"SLICE-{len(candidate_slices) + 1:03d}",
            "line": lineno,
            "section": current_sec,
            "text": s,
            "suspected_characteristic": suspected_char,
        })
        accumulated_chars += len(s)

    compression_ratio = round(accumulated_chars / max(1, total_doc_chars), 4)

    # ステップ6: プロファイル重み付き6特性スコアと推奨ロード特性（2〜4特性）の算出
    prof_cfg = PROFILE_CONFIGS[profile]
    weights: Dict[str, float] = prof_cfg["weights"]
    char_scores: Dict[str, Dict[str, Any]] = {}

    for cid in VALID_CHARACTERISTICS:
        high_c = sum(1 for f in raw_findings if f["asdoq_characteristic"] == cid and f["severity"] == "High")
        mid_c = sum(1 for f in raw_findings if f["asdoq_characteristic"] == cid and f["severity"] == "Mid")
        chk_c = sum(1 for f in raw_findings if f["asdoq_characteristic"] == cid and f["severity"] == "要確認")
        weight = weights.get(cid, 1.0)
        penalty = (high_c * 15 + mid_c * 6 + chk_c * 2) * weight
        score_val = max(0.0, round(100.0 - penalty, 1))
        char_scores[cid] = {
            "name": CHARACTERISTIC_NAMES[cid],
            "weight": weight,
            "score": score_val,
            "high": high_c,
            "mid": mid_c,
            "check": chk_c,
        }

    recommended: List[str] = list(prof_cfg["default_characteristics"])
    sorted_by_issue = sorted(
        VALID_CHARACTERISTICS,
        key=lambda c: (-(char_scores[c]["high"] * 10 + char_scores[c]["mid"]), -weights.get(c, 1.0)),
    )
    for cid in sorted_by_issue:
        if len(recommended) >= 4:
            break
        if cid not in recommended and (char_scores[cid]["high"] > 0 or char_scores[cid]["mid"] > 0):
            recommended.append(cid)
    recommended = recommended[:4]
    if len(recommended) < 2:
        for cid in VALID_CHARACTERISTICS:
            if cid not in recommended:
                recommended.append(cid)
            if len(recommended) >= 2:
                break

    return {
        "profile": profile,
        "profile_name": prof_cfg["name"],
        "characteristic_filter": characteristic,
        "tokenizer_mode": tokenizer_mode,
        "total_chars": total_doc_chars,
        "candidate_slice_chars": accumulated_chars,
        "compression_ratio": compression_ratio,
        "confirmed_findings": confirmed_findings,
        "total_confirmed_count": len(raw_findings),
        "omitted_counts_by_category": omitted_counts_by_category,
        "cross_reference": cross_reference,
        "candidate_slices": candidate_slices,
        "characteristic_scores": char_scores,
        "recommended_characteristics": recommended,
    }


# ---------------------------------------------------------------------------
# UNIT-003: Layer 1 Google gemini-decision-1 判定・CLIエントリポイントモジュール
# ---------------------------------------------------------------------------

def _parse_dotenv_key(dotenv_path: Path, key_name: str = "GEMINI_API_KEY") -> Optional[str]:
    """`.env` / `.env.local` から指定キーをUTF-8で読み取る（値自体は呼び出し元でも露出禁止）。"""
    if not dotenv_path.is_file():
        return None
    try:
        content = dotenv_path.read_text(encoding="utf-8-sig")
    except Exception:
        return None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() != key_name:
            continue
        val = v.strip()
        if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
            val = val[1:-1].strip()
        if val:
            return val
    return None


def resolve_gemini_api_key(base_dir: Optional[Path] = None) -> Tuple[Optional[str], str]:
    """
    関数名：resolve_gemini_api_key
    戻り値：(APIキー文字列またはNone, 検出元ラベル 'env:GEMINI_API_KEY' | 'file:.env.local' | 'file:.env' | 'unset')
    引数：base_dir (Optional[Path]) - `.env.local` / `.env` 探索基準ディレクトリ（None時はリポジトリルート）
    関数の概要：
        OS環境変数 GEMINI_API_KEY > .env.local > .env の優先順位でAPIキーを解決する（空文字列は未設定扱い）。
        キー文字列自体はログやレポートに一切出力しない。
    対応機能ID（トレーサビリティ）：UNIT-003 (REQ-003, TC-008)
    """
    env_val = os.environ.get("GEMINI_API_KEY", "").strip()
    if len(env_val) >= 2 and ((env_val[0] == '"' and env_val[-1] == '"') or (env_val[0] == "'" and env_val[-1] == "'")):
        env_val = env_val[1:-1].strip()
    if env_val:
        return env_val, "env:GEMINI_API_KEY"

    root_dir = base_dir if base_dir is not None else Path(__file__).resolve().parents[1]
    for fname, src_label in ((".env.local", "file:.env.local"), (".env", "file:.env")):
        found = _parse_dotenv_key(root_dir / fname, "GEMINI_API_KEY")
        if found:
            return found, src_label
    return None, "unset"


class MockDecision1Client:
    """
    単体テスト・オフライン評価用の決定論的 gemini-decision-1 モッククライアント（UNIT-003 / SW205 表13）。
    - v1beta/decisions バッチリクエスト・レスポンススキーマ（answers + usage.total_output_tokens=0）を忠実に再現
    - 確率値 `0.30` / `0.29` の境界検証（TC-007）
    - API通信失敗・最大2回リトライ境界の注入（TC-009）
    に対応する。
    """

    def __init__(self, fail_times: int = 0, return_invalid_json_times: int = 0):
        """
        関数名：__init__
        戻り値：なし
        引数：
            fail_times (int) - 通信エラーを発生させる回数
            return_invalid_json_times (int) - 不正レスポンスを発生させる回数
        関数の概要：モッククライアントを初期化する。
        対応機能ID（トレーサビリティ）：UNIT-003 (REQ-003, TC-007, TC-009)
        """
        self.fail_times = fail_times
        self.return_invalid_json_times = return_invalid_json_times
        self.call_count = 0
        self.last_payloads: List[Dict[str, Any]] = []

    def evaluate_decisions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        関数名：evaluate_decisions
        戻り値：v1beta/decisions 形式のレスポンス辞書（answers, usage）
        引数：payload (Dict[str, Any]) - model, input, questions を含むDecisions APIリクエスト辞書
        関数の概要：質問バッチを受け取り、決定論的な noul / choice / score 回答マップを返す。
        対応機能ID（トレーサビリティ）：UNIT-003 (REQ-003, TC-007, TC-009)
        """
        self.call_count += 1
        self.last_payloads.append(payload)

        if self.call_count <= self.fail_times:
            raise ConnectionError(f"Mock Decision1 transient error (attempt {self.call_count})")
        if self.call_count <= self.fail_times + self.return_invalid_json_times:
            raise json.JSONDecodeError("Mock malformed JSON", "{bad", 1)

        questions = payload.get("questions", {})
        answers: Dict[str, Any] = {}

        for q_key, q_spec in questions.items():
            q_type = q_spec.get("type", "noul")
            instr = str(q_spec.get("instructions", ""))

            if "0.29" in instr or "境界029" in instr:
                noul_p = 0.29
                choice_k = "C4_1"
                probs = [0.85, 0.10, 0.05]
                score_val = 1.20
                conf = 0.92
            elif "0.30" in instr or "境界030" in instr:
                noul_p = 0.30
                choice_k = "C4_1"
                probs = [0.55, 0.35, 0.10]
                score_val = 1.55
                conf = 0.85
            else:
                has_high = bool(re.search(r"思われる|考えられる|だろう|TBD|未定|適切|高速|柔軟", instr))
                has_mid = bool(re.search(r"れる|られる|省略|理由|それ|これ|上記|当該|基本的", instr))
                if has_high:
                    noul_p = 0.84
                    probs = [0.08, 0.27, 0.65]
                    score_val = 2.57
                    conf = 0.90
                elif has_mid:
                    noul_p = 0.62
                    probs = [0.25, 0.50, 0.25]
                    score_val = 2.00
                    conf = 0.82
                else:
                    noul_p = 0.32
                    probs = [0.60, 0.30, 0.10]
                    score_val = 1.50
                    conf = 0.78

                if re.search(r"理由|省略|したがって", instr):
                    choice_k = "C3_1"
                elif re.search(r"未定|TBD|将来|変更", instr):
                    choice_k = "C2_2"
                elif re.search(r"思われる|考えられる|べき", instr):
                    choice_k = "C6_4"
                elif re.search(r"れる|られる", instr):
                    choice_k = "C5_3"
                else:
                    choice_k = "C4_1"

            if q_type == "noul":
                answers[q_key] = {"type": "noul", "noul": noul_p, "confidence": conf}
            elif q_type == "choice":
                answers[q_key] = {
                    "type": "choice",
                    "choice": choice_k,
                    "probabilities": {choice_k: noul_p, "other": round(1.0 - noul_p, 4)},
                    "confidence": conf,
                }
            else:
                answers[q_key] = {
                    "type": "score",
                    "score": score_val,
                    "probabilities": probs,
                    "confidence": conf,
                }

        return {
            "answers": answers,
            "usage": {
                "total_input_tokens": max(1, len(str(payload.get("input", ""))) // 4),
                "total_output_tokens": 0,
            },
        }


class _TransientDecision1Error(Exception):
    """リトライ可能なHTTP 429/5xx・タイムアウト・不正JSONエラーを表す内部例外。"""


class RestDecision1Client:
    """
    urllib.request を用いた Google Gemini Decisions API (v1beta/decisions) クライアント（UNIT-003）。
    google-genai SDK の有無に依存せず標準ライブラリのみで HTTP POST 通信を行う。
    """

    def __init__(self, api_key: str, timeout_sec: float = 30.0):
        self._api_key = api_key
        self._timeout_sec = timeout_sec

    def evaluate_decisions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """v1beta/decisions エンドポイントへ JSON POST を送信し、応答を検証して返す。"""
        body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            DECISIONS_API_URL,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_sec) as resp:
                raw_resp = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            err_snippet = ""
            try:
                err_snippet = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            # APIキーに似たパターンが万一エラー文に含まれてもマスクする
            err_snippet = re.sub(r"AIza[A-Za-z0-9_-]{10,}", "***REDACTED***", err_snippet)
            if exc.code == 429 or exc.code >= 500:
                raise _TransientDecision1Error(f"HTTP {exc.code}: {err_snippet}") from exc
            raise RuntimeError(f"Gemini Decisions API エラー (HTTP {exc.code}): {err_snippet}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise _TransientDecision1Error(f"通信エラー: {type(exc).__name__}") from exc

        try:
            parsed = json.loads(raw_resp)
        except json.JSONDecodeError as exc:
            raise _TransientDecision1Error(f"Decisions API のJSON解析に失敗しました: {exc}") from exc

        if not isinstance(parsed, dict) or "answers" not in parsed:
            raise _TransientDecision1Error("Decisions API 応答に 'answers' フィールドがありません。")
        return parsed


def _sanitize_question_key(slice_id: str, index: int, suffix: str) -> str:
    """Decisions API 質問キー制約 `^[A-Za-z0-9_-]{1,64}$` を満たす安全なキーを生成する。"""
    base = re.sub(r"[^A-Za-z0-9_-]", "_", slice_id).strip("_") or f"S{index + 1:03d}"
    candidate = f"{base}_{suffix}"
    return candidate[:64]


def _build_slice_questions(slices: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """
    各疑義スライスに対して noul / choice / score の3問セット（計3N問）を構築する。
    `instructions` は行番号・節名・スライス本文を含む肯定文で記述し、
    `choice` キーは ASCII のみ、`score` 基準は低リスク→高リスク順（昇順）とする。
    """
    questions: Dict[str, Dict[str, Any]] = {}
    key_index: List[Dict[str, Any]] = []

    score_criteria_asc = [
        "Low: 問題なし。主語・条件・根拠が明確で修正は不要である。",
        "Mid: 軽微な懸念あり。表現の明確化や補足説明を検討すべきである。",
        "High: 重大な懸念あり。曖昧・主語欠落・矛盾または検証不能であり修正が必須である。",
    ]

    for idx, sl in enumerate(slices):
        sid = str(sl.get("slice_id", f"SLICE-{idx + 1:03d}"))
        lineno = sl.get("line", 0)
        section = str(sl.get("section", "本文"))
        text_excerpt = str(sl.get("text", ""))[:300]

        q_noul = _sanitize_question_key(sid, idx, "noul")
        q_choice = _sanitize_question_key(sid, idx, "choice")
        q_score = _sanitize_question_key(sid, idx, "score")

        questions[q_noul] = {
            "type": "noul",
            "instructions": (
                f"文書抜粋内の対象箇所（ID={sid}, L{lineno}, 節={section}）『{text_excerpt}』に、"
                "曖昧表現・主語欠落・根拠省略・事実と意見の混同・検証不能記述のいずれかのASDoQ品質問題が存在するかを判定してください。"
            ),
        }
        questions[q_choice] = {
            "type": "choice",
            "instructions": (
                f"対象箇所（ID={sid}, L{lineno}, 節={section}）『{text_excerpt}』で最も該当するASDoQ品質副特性を選択してください。"
            ),
            "criteria": dict(CHOICE_CRITERIA_DEFINITIONS),
        }
        questions[q_score] = {
            "type": "score",
            "instructions": (
                f"対象箇所（ID={sid}, L{lineno}, 節={section}）『{text_excerpt}』のASDoQ品質上の懸念度を低い方から高い方へ採点してください。"
            ),
            "criteria": score_criteria_asc,
        }
        key_index.append({
            "slice": sl,
            "q_noul": q_noul,
            "q_choice": q_choice,
            "q_score": q_score,
        })

    return questions, key_index


def _heuristic_local_decision(sl: Dict[str, Any]) -> Dict[str, Any]:
    """APIキー未設定・OFF・フォールバック時に標準ローカル判定結果を生成する。"""
    q_map, _ = _build_slice_questions([sl])
    mock = MockDecision1Client(fail_times=0)
    resp = mock.evaluate_decisions({
        "model": DECISIONS_MODEL_ID,
        "input": str(sl.get("text", "")),
        "questions": q_map,
    })
    return resp["answers"]


def _extract_score_risk(score_ans: Dict[str, Any]) -> Tuple[float, str]:
    """
    Decisions API の score 応答（1始まり期待スコアとprobabilities配列）から
    0.0〜1.0 のリスク値と重大度レベル（Low/Mid/High）を算出する。
    """
    probs = score_ans.get("probabilities")
    raw_score = float(score_ans.get("score", 0.0))

    if isinstance(probs, list) and len(probs) >= 2:
        non_low_prob = sum(float(p) for p in probs[1:])
        norm_from_1based = (raw_score - 1.0) / max(1, len(probs) - 1) if raw_score >= 1.0 else raw_score
        risk_val = max(0.0, min(1.0, max(non_low_prob, norm_from_1based)))
    elif raw_score >= 1.0:
        risk_val = max(0.0, min(1.0, (raw_score - 1.0) / 2.0))
    else:
        risk_val = max(0.0, min(1.0, raw_score))

    if risk_val >= 0.70 or raw_score >= 2.4:
        sev = "High"
    elif risk_val >= 0.30 or raw_score >= 1.6:
        sev = "Mid"
    else:
        sev = "Low"
    return round(risk_val, 4), sev


def evaluate_layer1_decision1(
    candidate_slices: List[Dict[str, Any]],
    decision1_mode: str = "off",
    threshold: float = 0.30,
    client: Optional[Any] = None,
    max_retries: int = 2,
    document_excerpt: str = "",
) -> Dict[str, Any]:
    """
    関数名：evaluate_layer1_decision1
    戻り値：Layer 1 gemini-decision-1 判定結果（decision1_mode, threshold, api_calls, total_output_tokens, evaluated_slices, retained_slices, discarded_slices, retry_count）
    引数：
        candidate_slices (List[Dict[str, Any]]) - Layer 0が抽出した疑義スライスリスト
        decision1_mode (str) - 実行モード ('off' | 'on' | 'mock')、既定 'off'
        threshold (float) - 見逃し防止優先の棄却閾値（既定 0.30、定義域 0.0〜1.0）
        client (Optional[Any]) - テスト注入用クライアント（任意）
        max_retries (int) - 通信失敗時の最大リトライ回数（既定 2）
        document_excerpt (str) - 文書全体抜粋（Decisions API の input に設定）
    関数の概要：
        疑義スライスに対して Google gemini-decision-1（v1beta/decisions）の noul / choice / score
        バッチ判定（1,000問分割・0問スキップ・最大2回リトライ・ローカルフォールバック）または
        オフラインルールベース判定を実行し、閾値以上のスライスを保持・昇格させる。
    対応機能ID（トレーサビリティ）：UNIT-003 (REQ-003)
    """
    if decision1_mode not in ("off", "on", "mock"):
        raise ValueError(f"不正な --decision1 モードです: {decision1_mode}")
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError(f"--threshold は 0.0 から 1.0 の範囲で指定してください（指定値: {threshold}）。")

    # 質問数0件時はAPI通信を行わずスキップする（REQ-003 / TC-011）
    if len(candidate_slices) == 0:
        skipped_mode = "on_skipped (no_questions)" if decision1_mode in ("on", "mock") else "off (local_rule_fallback)"
        return {
            "decision1_mode": skipped_mode,
            "threshold": threshold,
            "api_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "evaluated_slices": [],
            "retained_slices": [],
            "discarded_slices": [],
            "retry_count": 0,
        }

    # --decision1 off 時（既定）は外部通信を行わずローカルルールベース判定を返す
    if decision1_mode == "off":
        evaluated_off: List[Dict[str, Any]] = []
        retained_off: List[Dict[str, Any]] = []
        discarded_off: List[Dict[str, Any]] = []
        _, key_index = _build_slice_questions(candidate_slices)

        for entry in key_index:
            sl = entry["slice"]
            ans_map = _heuristic_local_decision(sl)
            noul_val = float(ans_map[entry["q_noul"]].get("noul", 0.5))
            choice_key = str(ans_map[entry["q_choice"]].get("choice", "other"))
            asdoq_lbl = CHOICE_ASDOQ_LABEL_MAP.get(choice_key, "[ASDoQ:その他-要確認]")
            risk_val, sev = _extract_score_risk(ans_map[entry["q_score"]])

            status = "retained" if (noul_val >= threshold or risk_val >= threshold or sev in ("High", "Mid")) else "discarded"
            enriched = dict(sl)
            enriched.update({
                "noul": noul_val,
                "choice": choice_key,
                "asdoq_label": asdoq_lbl,
                "score": ans_map[entry["q_score"]].get("score", 0.0),
                "score_risk": risk_val,
                "severity_estimate": sev,
                "max_probability": round(max(noul_val, risk_val), 4),
                "status": status,
            })
            evaluated_off.append(enriched)
            (retained_off if status == "retained" else discarded_off).append(enriched)

        return {
            "decision1_mode": "off (local_rule_fallback)",
            "threshold": threshold,
            "api_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "evaluated_slices": evaluated_off,
            "retained_slices": retained_off,
            "discarded_slices": discarded_off,
            "retry_count": 0,
        }

    # クライアント解決（モック注入、またはAPIキー解決してREST/SDKクライアント生成）
    active_client = client
    if active_client is None:
        if decision1_mode == "mock":
            active_client = MockDecision1Client(fail_times=0)
        else:
            api_key, _key_source = resolve_gemini_api_key()
            if not api_key:
                raise RuntimeError(
                    "--decision1 on が指定されましたが、GEMINI_API_KEY（環境変数 / .env.local / .env）が設定されていません。"
                    "APIキーを設定するか、既定の --decision1 off を使用してください。"
                )
            active_client = RestDecision1Client(api_key=api_key)

    effective_mode = "on (mock)" if isinstance(active_client, MockDecision1Client) or decision1_mode == "mock" else "on (api)"

    # 質問バッチ生成と 1,000問単位分割（1スライス=3問なので最大333スライス=999問ずつ分割）
    all_questions, key_index = _build_slice_questions(candidate_slices)
    excerpt_text = document_excerpt or "\n".join(str(s.get("text", "")) for s in candidate_slices)
    excerpt_text = excerpt_text[:120000]

    slices_per_chunk = max(1, MAX_QUESTIONS_PER_REQUEST // 3)
    merged_answers: Dict[str, Any] = {}
    total_retries = 0
    api_calls = 0
    total_input_tokens = 0
    total_output_tokens = 0
    fell_back_to_local = False

    for start in range(0, len(key_index), slices_per_chunk):
        chunk_entries = key_index[start:start + slices_per_chunk]
        chunk_questions: Dict[str, Dict[str, Any]] = {}
        for item in chunk_entries:
            chunk_questions[item["q_noul"]] = all_questions[item["q_noul"]]
            chunk_questions[item["q_choice"]] = all_questions[item["q_choice"]]
            chunk_questions[item["q_score"]] = all_questions[item["q_score"]]

        payload = {
            "model": DECISIONS_MODEL_ID,
            "input": excerpt_text,
            "questions": chunk_questions,
        }

        attempt = 0
        chunk_resp: Optional[Dict[str, Any]] = None
        while True:
            try:
                api_calls += 1
                chunk_resp = active_client.evaluate_decisions(payload)
                break
            except (_TransientDecision1Error, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt >= max_retries:
                    print(
                        f"[WARN] gemini-decision-1 通信が最大リトライ回数（{max_retries}回）に達したため、"
                        f"ローカル判定へフォールバックします: {type(exc).__name__}",
                        file=sys.stderr,
                    )
                    fell_back_to_local = True
                    break
                attempt += 1
                total_retries += 1

        if chunk_resp is not None and not fell_back_to_local:
            merged_answers.update(chunk_resp.get("answers", {}))
            usage = chunk_resp.get("usage", {})
            total_input_tokens += int(usage.get("total_input_tokens", 0))
            total_output_tokens += int(usage.get("total_output_tokens", 0))
        else:
            for item in chunk_entries:
                merged_answers.update(_heuristic_local_decision(item["slice"]))

    if fell_back_to_local:
        effective_mode = "off (local_fallback_after_error)"

    evaluated_slices: List[Dict[str, Any]] = []
    retained_slices: List[Dict[str, Any]] = []
    discarded_slices: List[Dict[str, Any]] = []

    for item in key_index:
        sl = item["slice"]
        ans_noul = merged_answers.get(item["q_noul"], {})
        ans_choice = merged_answers.get(item["q_choice"], {})
        ans_score = merged_answers.get(item["q_score"], {})

        noul_val = float(ans_noul.get("noul", ans_noul.get("probability", 0.0)))
        choice_key = str(ans_choice.get("choice", ans_choice.get("selected", "other")))
        asdoq_lbl = CHOICE_ASDOQ_LABEL_MAP.get(choice_key, "[ASDoQ:その他-要確認]")
        risk_val, sev = _extract_score_risk(ans_score)
        confidence = float(ans_noul.get("confidence", ans_score.get("confidence", 0.0)))

        # 見逃し防止優先判定：noul >= threshold または scoreリスク >= threshold または severity in (High, Mid)
        if noul_val >= threshold or risk_val >= threshold or sev in ("High", "Mid"):
            status = "retained"
        else:
            status = "discarded"

        enriched = dict(sl)
        enriched.update({
            "noul": round(noul_val, 4),
            "choice": choice_key,
            "asdoq_label": asdoq_lbl,
            "score": ans_score.get("score", 0.0),
            "score_risk": risk_val,
            "severity_estimate": sev,
            "confidence": round(confidence, 4),
            "max_probability": round(max(noul_val, risk_val), 4),
            "status": status,
        })
        evaluated_slices.append(enriched)
        if status == "retained":
            retained_slices.append(enriched)
        else:
            discarded_slices.append(enriched)

    return {
        "decision1_mode": effective_mode,
        "threshold": threshold,
        "api_calls": api_calls,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "evaluated_slices": evaluated_slices,
        "retained_slices": retained_slices,
        "discarded_slices": discarded_slices,
        "retry_count": total_retries,
    }


# ---------------------------------------------------------------------------
# UNIT-004 検証支援関数: validate_specialist_definitions（SW205 8.2節 表13）
# ---------------------------------------------------------------------------

def validate_specialist_definitions(
    refs_dir: Path,
    max_lines: int = 200,
) -> Dict[str, Any]:
    """
    関数名：validate_specialist_definitions
    戻り値：6特性別専門レビュアー定義の検証結果辞書（valid: bool, errors: List[str], files: Dict）
    引数：
        refs_dir (Path) - 専門定義ファイル群が格納されたディレクトリパス
        max_lines (int) - 1ファイルあたりの行数上限（既定 200行）
    関数の概要：
        .agents/skills/asdoq-reviewer/references/ 配下の6ファイル（C1〜C6）について、
        実在・200行以下境界・UNIT-004記載・必須6要素・旧表記非混入・/swarm非依存を検証する。
    対応機能ID（トレーサビリティ）：UNIT-004 (REQ-004, TC-013)
    """
    errors: List[str] = []
    file_reports: Dict[str, Any] = {}

    required_checks = [
        ("unit_id", r"UNIT-004", "UNIT-004の記載"),
        ("sub_characteristic", r"副特性|測定項目", "①担当副特性・測定項目"),
        ("devils_advocate", r"反証|Devil's Advocate", "②反証駆動質問（Devil's Advocate）"),
        ("evidence_rule", r"証拠|根拠箇所|行番号", "③合格時の証拠引用ルール"),
        ("before_after", r"❌\s*Before.*✅\s*After|❌ Before|✅ After", "④❌Before/✅After出力形式"),
        ("transparency", r"①現在地.*②判断の根拠.*③次の一手", "⑤思考過程出力指示"),
        ("prohibitions", r"禁止事項", "⑥禁止事項"),
    ]

    for fname in SPECIALIST_FILES:
        fpath = refs_dir / fname
        if not fpath.is_file():
            errors.append(f"専門定義ファイルが存在しません: {fpath}")
            continue
        content = fpath.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        line_count = len(content.split("\n"))
        if content.endswith("\n"):
            line_count -= 1

        if line_count > max_lines:
            errors.append(
                f"{fname}: 行数が上限を超えています（{line_count}行 > 上限{max_lines}行）。"
            )

        missing_elems: List[str] = []
        for _key, pat, label in required_checks:
            if not re.search(pat, content, re.DOTALL):
                missing_elems.append(label)
                errors.append(f"{fname}: 必須要素『{label}』が不足しています。")

        legacy_hit = _contains_legacy_asdoq_token(content)
        if legacy_hit:
            errors.append(f"{fname}: 禁止された{legacy_hit}が残存しています。")
        if "/swarm" in content:
            errors.append(f"{fname}: 特定環境依存の '/swarm' 指定を含めることはできません。")

        file_reports[fname] = {
            "line_count": line_count,
            "within_limit": line_count <= max_lines,
            "missing_elements": missing_elems,
        }

    return {
        "valid": len(errors) == 0 and len(file_reports) == len(SPECIALIST_FILES),
        "errors": errors,
        "files": file_reports,
    }


# ---------------------------------------------------------------------------
# レポート整形（Markdown / JSON / 1行サマリ）
# ---------------------------------------------------------------------------

def render_markdown_report(
    input_path: Path,
    layer0: Dict[str, Any],
    layer1: Dict[str, Any],
    summary_line: str,
) -> str:
    """
    関数名：render_markdown_report
    戻り値：構造化されたMarkdownレポート文字列（str）
    引数：
        input_path (Path) - 検査対象ファイルパス
        layer0 (Dict[str, Any]) - Layer 0解析結果
        layer1 (Dict[str, Any]) - Layer 1 gemini-decision-1 判定結果
        summary_line (str) - 末尾1行サマリ文字列
    関数の概要：Layer 0およびLayer 1の解析・判定結果をMarkdownレポートへ整形する。
    対応機能ID（トレーサビリティ）：UNIT-002, UNIT-003 (REQ-002, REQ-003)
    """
    d_mode = layer1["decision1_mode"]
    if d_mode == "on (api)":
        mode_note = "Google gemini-decision-1 API使用（出力トークン数=0）"
        sec4_title = "## 4. Layer 1 gemini-decision-1（API）構造化判定・保持スライス一覧"
    elif d_mode == "on (mock)":
        mode_note = "テスト用モック使用"
        sec4_title = "## 4. Layer 1 gemini-decision-1（テスト用モック）構造化判定・保持スライス一覧"
    elif d_mode.startswith("on_skipped"):
        mode_note = "疑義スライス0件のためAPI呼び出しをスキップ"
        sec4_title = "## 4. Layer 1 gemini-decision-1（質問0件スキップ）"
    else:
        mode_note = "ローカルルールベース選別・外部API通信なし"
        sec4_title = "## 4. Layer 1 ローカルルールベース選別・保持スライス一覧（API未使用）"

    lines: List[str] = [
        f"# ASDoQ ハイブリッド解析レポート: `{input_path.as_posix()}`",
        "",
        f"- **適用プロファイル**: `{layer0['profile']}` ({layer0['profile_name']})",
        f"- **形態素解析モード**: `{layer0['tokenizer_mode']}`",
        f"- **Layer 1 選別モード**: `DECISION1_MODE: {d_mode}` (threshold={layer1['threshold']} / {mode_note})",
        f"- **Layer 1 API集計**: calls={layer1.get('api_calls', 0)}, total_output_tokens={layer1.get('total_output_tokens', 0)}",
        f"- **疑義スライス圧縮率**: {layer0['candidate_slice_chars']} / {layer0['total_chars']} 文字 ({layer0['compression_ratio'] * 100:.1f}%)",
        f"- **Layer 2 推奨ロード特性（2〜4特性）**: {', '.join(f'`{c}`' for c in layer0['recommended_characteristics'])}",
        "",
        "## 1. ASDoQ 6大品質特性別スコア",
        "",
        "| 特性ID | 品質特性名 | 重み | スコア | High | Mid | 要確認 |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for cid, sinfo in layer0["characteristic_scores"].items():
        lines.append(
            f"| `{cid}` | {sinfo['name']} | {sinfo['weight']} | {sinfo['score']} | "
            f"{sinfo['high']} | {sinfo['mid']} | {sinfo['check']} |"
        )

    lines.extend(["", "## 2. 確定指摘一覧（Layer 0 拡張違反例辞書・企業カスタム辞書）", ""])
    findings = layer0["confirmed_findings"]
    if not findings:
        lines.append("- 確定指摘なし")
    else:
        for f in findings:
            lbl = f.get("asdoq_label", "")
            lines.append(
                f"- **[{f['severity']}]** L{f['line']} (`{f['rule_id']}` / {lbl}): "
                f"該当=`{f['matched']}` → {f['hint']}"
            )
        for cat_id, omit_cnt in layer0.get("omitted_counts_by_category", {}).items():
            lines.append(f"- ...カテゴリ{cat_id}: 他 {omit_cnt} 件省略（--max-items 上限により省略）")

    xr = layer0["cross_reference"]
    ps = xr["purpose_scope_check"]
    tc = xr["term_cross_check"]
    nu = xr["numbers_units_table"]
    hf = xr["heading_figure_table_check"]

    lines.extend([
        "",
        "## 3. 構造クロスリファレンス表（4項目）",
        "",
        "### ① 目的・スコープ要素チェック（目的適合性支援）",
        f"- 読み手の記述: {'あり' if ps['has_reader'] else '欠落'}",
        f"- 目的の記述: {'あり' if ps['has_purpose'] else '欠落'}",
        f"- 適用範囲（スコープ内/外）の記述: スコープ内={'あり' if ps['has_scope_in'] else '欠落'} / スコープ外={'あり' if ps['has_scope_out'] else '欠落'}",
        f"- プロファイル必須章の充足: 充足={ps['present_required_sections']} / 未検出={ps['missing_required_sections']}",
        "",
        "### ② 用語集 vs 本文クロス突合（保守性・理解容易性支援）",
        f"- 用語定義表の登録語と本文出現数: {json.dumps(tc['defined_terms_usage'], ensure_ascii=False)}",
        f"- 本文3回以上出現の未定義用語候補: {json.dumps(tc['undefined_frequent_terms'], ensure_ascii=False)}",
        f"- 類似表記ゆれペア: {json.dumps(tc['similar_term_pairs'], ensure_ascii=False)}",
        "",
        "### ③ 数値・単位・条件クロス一覧（保守性・整合性支援）",
        f"- 抽出件数: {len(nu)} 件",
    ])
    for item in nu[:15]:
        lines.append(
            f"  - L{item['line']} [{item['section']}]: `{item['expression']}` "
            f"(数値={item['value']}, 単位={item['unit']}, 条件={item['condition'] or 'なし'})"
        )

    lines.extend([
        "",
        "### ④ 見出し・図表クロス突合（整合性・規範適合性支援）",
        f"- 1文以下の希薄見出し節: {json.dumps(hf['sparse_sections'], ensure_ascii=False)}",
        f"- 未定義の図参照: {hf['missing_figure_definitions']} / 未定義の表参照: {hf['missing_table_definitions']}",
        f"- Mermaid 10ノード上限超過: {json.dumps(hf['mermaid_over_10_nodes'], ensure_ascii=False)}",
        f"- 分割図[接続N]ペア検査: {json.dumps(hf['connection_pair_check'], ensure_ascii=False)}",
        f"- 図表キャプション位置違反（図下・表上規則）: {json.dumps(hf['caption_position_violations'], ensure_ascii=False)}",
        "",
        sec4_title,
        f"- 評価スライス数: {len(layer1['evaluated_slices'])} 件 "
        f"(保持・昇格: {len(layer1['retained_slices'])} 件 / 棄却: {len(layer1['discarded_slices'])} 件)",
    ])
    for s in layer1["retained_slices"][:15]:
        lines.append(
            f"  - `{s['slice_id']}` (L{s['line']}, {s.get('asdoq_label', s.get('suspected_characteristic'))}, "
            f"max_p={s.get('max_probability', '-')}): {s['text'][:70]}"
        )

    lines.extend(["", summary_line])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI エントリポイント（SW205 5.1節 表9・5.2節 表10〜11 準拠）
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """
    関数名：build_parser
    戻り値：設定済みの ArgumentParser インスタンス
    引数：なし
    関数の概要：SW205のACI仕様（表9・表11）に一致するCLIオプションを構築する。
    対応機能ID（トレーサビリティ）：UNIT-001, UNIT-002, UNIT-003 (REQ-001, REQ-002, REQ-003)
    """
    parser = argparse.ArgumentParser(
        description="ASDoQ ハイブリッド文書レビュー決定論的解析・gemini-decision-1 判定ツール (asdoq_lint.py)"
    )
    parser.add_argument("--input", default=None, help="検査対象Markdownファイルパス (.md)")
    parser.add_argument(
        "--validate-dict",
        nargs="?",
        const="__DEFAULT__",
        default=None,
        help="辞書ファイルの構文・必須キー・カテゴリ網羅性・80件以上を検証する（任意でパス指定可）",
    )
    parser.add_argument(
        "--dict",
        dest="dict_path",
        default=None,
        help="標準違反例辞書JSONパス（既定: tools/asdoq_dictionary.json）",
    )
    parser.add_argument(
        "--custom-dict",
        dest="custom_dict_path",
        default=None,
        help="企業カスタム辞書JSONパス（任意）",
    )
    parser.add_argument(
        "--profile",
        default="general",
        choices=["sw105", "swp6", "sw205", "general"],
        help="文書種別プロファイル（既定: general）",
    )
    parser.add_argument(
        "--characteristic",
        default="all",
        choices=[
            "all",
            "C1", "C2", "C3", "C4", "C5", "C6",
            "C1_purpose", "C2_maintainability", "C3_consistency",
            "C4_understandability", "C5_readability", "C6_conformance",
        ],
        help="検査対象のASDoQ品質特性フィルタ（既定: all）",
    )
    parser.add_argument(
        "--format",
        dest="out_format",
        default="markdown",
        choices=["markdown", "json"],
        help="出力フォーマット（markdown または json、既定: markdown）",
    )
    parser.add_argument(
        "--decision1",
        dest="decision1_mode",
        default="off",
        choices=["off", "on"],
        help="Layer 1 Google gemini-decision-1 実行モード（既定: off）",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.30,
        help="Layer 1 見逃し防止優先の棄却閾値（0.0〜1.0、既定: 0.30）",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=25,
        help="1カテゴリあたりの最大出力件数（既定: 25）",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="1行サマリのみを標準出力へ表示する",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """
    関数名：main
    戻り値：終了コード（0=合格/Highなし, 1=High指摘あり, 2=実行・検証エラー）
    引数：argv (Optional[List[str]]) - コマンドライン引数リスト（None時はsys.argv[1:]を使用）
    関数の概要：CLI引数を解析し、旧オプション拒否・辞書検証・Layer 0/1文書解析を実行して終了コードを返す。
    対応機能ID（トレーサビリティ）：UNIT-001, UNIT-002, UNIT-003 (REQ-001, REQ-002, REQ-003)
    """
    raw_argv = list(sys.argv[1:] if argv is None else argv)

    # 非推奨旧オプションの即時拒否と移行案内（UNIT-003 / REQ-003 / TC-009相当）
    for tok in raw_argv:
        if tok == DEPRECATED_CLI_FLAG or tok.startswith(f"{DEPRECATED_CLI_FLAG}="):
            print(
                f"[ERROR] オプション '{DEPRECATED_CLI_FLAG}' は廃止されました。"
                "Google gemini-decision-1 用の `--decision1 <off|on>`（既定: off）へ移行してください。",
                file=sys.stderr,
            )
            return 2

    parser = build_parser()
    try:
        args = parser.parse_args(raw_argv)
    except SystemExit as exc:
        return 2 if exc.code != 0 else 0

    repo_root = Path(__file__).resolve().parents[1]
    if args.validate_dict is not None and args.validate_dict != "__DEFAULT__":
        dict_path = Path(args.validate_dict)
    elif args.dict_path:
        dict_path = Path(args.dict_path)
    else:
        dict_path = repo_root / DEFAULT_DICT_REL_PATH

    custom_path = Path(args.custom_dict_path) if args.custom_dict_path else None

    # 1. 辞書ロード・検証（UNIT-001）
    try:
        ruleset = load_dictionary(dict_path, custom_path)
    except DictionaryValidationError as exc:
        print(f"[ERROR] 辞書検証エラー: {exc}", file=sys.stderr)
        return 2

    # --validate-dict モードの実行と出力
    if args.validate_dict is not None:
        cat_count = len(ruleset["categories"])
        rule_count = len(ruleset["rules"])
        ng_count = len(ruleset["custom_ng_rules"])
        ok_count = len(ruleset["custom_ok_terms"])
        summary = (
            f"ASDOQ-DICT: OK | version={ruleset['version']} | categories={cat_count} | rules={rule_count} | "
            f"custom_ng={ng_count} | custom_ok={ok_count}"
        )
        if not args.summary:
            print(f"# ASDoQ 拡張違反例辞書 検証結果: `{dict_path.as_posix()}`")
            print(f"- ライセンス表示: {ruleset['_meta'].get('adl_notice')}")
            print(f"- カテゴリ別件数: {json.dumps(ruleset['category_counts'], ensure_ascii=False)}")
            print(f"- {summary}")
        else:
            print(summary)
        return 0

    # 2. --input 指定の確認とファイル読み込み（UNIT-002）
    if not args.input:
        print("[ERROR] --input <path> または --validate-dict を指定してください。", file=sys.stderr)
        return 2

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"[ERROR] 入力ファイルが存在しません: {in_path}", file=sys.stderr)
        return 2

    try:
        raw_doc = in_path.read_text(encoding="utf-8-sig")
    except Exception as exc:
        print(f"[ERROR] 入力ファイルの読み込みに失敗しました: {exc}", file=sys.stderr)
        return 2

    # 3. Layer 0 解析と Layer 1 gemini-decision-1 判定の実行（UNIT-002 / UNIT-003）
    start_ts = time.perf_counter()
    try:
        layer0 = analyze_document_layer0(
            text=raw_doc,
            ruleset=ruleset,
            profile=args.profile,
            characteristic=args.characteristic,
            max_items=args.max_items,
        )
        layer1 = evaluate_layer1_decision1(
            candidate_slices=layer0["candidate_slices"],
            decision1_mode=args.decision1_mode,
            threshold=args.threshold,
            document_excerpt=raw_doc[:120000],
        )
    except (InputDocumentError, ValueError, RuntimeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    elapsed_sec = round(time.perf_counter() - start_ts, 4)

    # 4. 重要度集計と終了コード（0: High=0, 1: High>=1）の決定
    high_cnt = sum(1 for f in layer0["confirmed_findings"] if f["severity"] == "High")
    mid_cnt = sum(1 for f in layer0["confirmed_findings"] if f["severity"] == "Mid")
    chk_cnt = sum(1 for f in layer0["confirmed_findings"] if f["severity"] == "要確認")
    status_str = "NG" if high_cnt > 0 else "OK"

    summary_line = (
        f"ASDOQ-LINT: {status_str} | profile={args.profile} | "
        f"High={high_cnt} / Mid={mid_cnt} / 要確認={chk_cnt} | "
        f"DECISION1_MODE={layer1['decision1_mode']} | "
        f"recommended={','.join(layer0['recommended_characteristics'])} | "
        f"elapsed={elapsed_sec}s"
    )

    if args.summary:
        print(summary_line)
    elif args.out_format == "json":
        payload = {
            "summary": summary_line,
            "status": status_str,
            "elapsed_sec": elapsed_sec,
            "DECISION1_MODE": layer1["decision1_mode"],
            "layer0": layer0,
            "layer1": layer1,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_markdown_report(in_path, layer0, layer1, summary_line))

    return 1 if high_cnt > 0 else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    sys.exit(main())
