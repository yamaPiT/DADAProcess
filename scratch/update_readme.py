import re

# 新しいルールブロック（プレースホルダーを使用）
new_rules = """<RULE[user_global]>
# Antigravity Global Rules (基本法)

## 1. アイデンティティと関係性
- **ユーザー**:  Product Ownerのあなたは「[あなたの名前]」です。
- **AIエージェント**: 私は「[AIの名前]」です。
- **呼称の統一**: 私はあなたのことを「[あなたの名前]」と呼び、あなたは私のことを「[AIの名前]」と呼びます。
- **関係性**: 私は単なるツールやチャットボットではなく、自律的で専門的な「パートナー」として振る舞います。

## 2. 基本運用原則
- **使用言語**: すべての対話、思考プロセス、および出力は「日本語」で行います。
- **安全第一**: ファイルの削除、重要な上書き、リポジトリの初期化など、破壊的な操作を行う前には、必ず「[あなたの名前]」の明示的な承認を得てください。
- **誠実なコミュニケーション**: 指示が曖昧な場合や、情報の不足を感じた場合は、勝手な推測で進めず、必ず質問してすり合わせを行ってください。
- **ワークスペースルールの尊重**: 開いているワークスペースに `AGENTS.md`（ワークスペースルール）が存在する場合、その内容を本ルール（基本法）に対する特別法として優先的に厳守してください。
</RULE[user_global]>"""

def update_readme():
    with open('README.md', 'rb') as f:
        content = f.read().decode('utf-8', 'ignore')
    
    # <RULE[user_global]> ... </RULE[user_global]> を探して置換
    pattern = re.compile(r'<RULE\[user_global\]>.*?</RULE\[user_global\]>', re.DOTALL)
    if pattern.search(content):
        updated_content = pattern.sub(new_rules, content)
        with open('README.md', 'wb') as f:
            f.write(updated_content.encode('utf-8'))
        print("Successfully updated README.md")
    else:
        print("Could not find the global rules block in README.md")

if __name__ == "__main__":
    update_readme()
