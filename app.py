import os
import json
import sqlite3
import requests
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime

# 加载配置
load_dotenv()
API_KEY = os.getenv("MOONSHOT_API_KEY")
DB_PATH = 'game_history.db'

app = Flask(__name__, static_folder='static')
CORS(app)


@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()

    if not username:
        return jsonify({"error": "用户名不能为空"}), 400

    db = get_db()
    try:
        # 尝试插入新用户 (如果不存在则插入成功，存在则报错 IntegrityError)
        db.execute('INSERT INTO users (username) VALUES (?)', (username,))
        db.commit()
        msg = f"欢迎新用户 {username}!"
    except sqlite3.IntegrityError:
        msg = f"欢迎回来, {username}!"

    return jsonify({"status": "success", "username": username, "message": msg})


@app.route('/api/get_user_stats', methods=['GET'])
def get_user_stats():
    # 这里暂时从前端传递 username，实际生产应从 Session 获取
    username = request.args.get('username')
    if not username:
        return jsonify({"error": "未登录"}), 401

    db = get_db()
    # 获取该用户的总游戏数
    total_games = db.execute('SELECT COUNT(*) FROM game_history WHERE username = ?', (username,)).fetchone()[0]
    # 获取该用户的平均猜测次数
    avg_attempts = db.execute('SELECT AVG(attempts) FROM game_history WHERE username = ?', (username,)).fetchone()[0]

    return jsonify({
        "total_games": total_games,
        "avg_attempts": round(avg_attempts, 1) if avg_attempts else 0
    })

# --- 数据库管理模块 ---
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """初始化数据库表"""
    # 注意：这里使用绝对路径或者相对路径都要小心
    # 在 Render 上，当前目录是 /opt/render/project/src
    # 所以 'game_history.db' 会创建在这个目录下，这是正确的

    with sqlite3.connect(DB_PATH) as conn:  # DB_PATH = 'game_history.db'
        # 创建用户表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建游戏记录表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS game_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                target_word TEXT NOT NULL,
                clue_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                attempts INTEGER DEFAULT 0,
                hints INTEGER DEFAULT 0,
                FOREIGN KEY(username) REFERENCES users(username)
            )
        ''')
        conn.commit()


def get_history_words(username, limit=50):
    db = get_db()
    cur = db.execute('SELECT target_word FROM game_history WHERE username = ? ORDER BY created_at DESC LIMIT ?', (username, limit))
    return [row['target_word'] for row in cur.fetchall()]


# 辅助函数修改：保存时带上 username
def save_game_result(username, word, clue, attempts, hints):
    try:
        db = get_db()
        db.execute('INSERT INTO game_history (username, target_word, clue_text, attempts, hints) VALUES (?, ?, ?, ?, ?)',
                   (username, word, clue, attempts, hints))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False


# --- AI 服务模块 ---
def call_ai(messages):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "moonshot-v1-8k",
        "messages": messages,
        "temperature": 0.7
    }
    resp = requests.post("https://api.moonshot.cn/v1/chat/completions", headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


# --- 路由接口 ---

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/init_game', methods=['GET'])
def init_game():
    """
    核心逻辑：
    1. 获取历史题目。
    2. 让 AI 生成一个【新词】 + 【描述】，且新词不能出现在历史中。
    3. 返回给前端（注意：实际生产中 target_word 不应明文返回，这里为了演示逻辑暂且返回，或改为后端维护 Session）
    """
    username = request.args.get('username')
    if not username:
        return jsonify({"error": "未登录"}), 401

    # 只获取当前用户的历史题目
    history = get_history_words(username, 50)
    history_str = "、".join(history) if history else "无"

    system_prompt = "你是一个百科猜词游戏的出题官。你需要生成一个词语和一段对应的描述。"
    user_prompt = f"""
    请生成一个新的猜词题目。
    要求：
    1. **词语要求**：必须是中文名词（2-6个字），涉及科技、生活、自然、运动等领域。
    2. **去重要求**：绝对不能是以下已经出过的词：[{history_str}]。如果生成了重复词，请重新思考一个完全不同的。
    3. **描述要求**：写一段 150-250 字的描述，生动有趣，包含关键特征，但**绝对不能直接出现该词语本身**。
    4. **输出格式**：严格只返回 JSON 格式，不要 Markdown 标记。格式如下：
       {{
         "word": "生成的词语",
         "clue": "生成的描述文本"
       }}
    """

    try:
        content = call_ai([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        # 清理可能的 Markdown 标记
        content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)

        word = data.get('word')
        clue = data.get('clue')

        if not word or not clue:
            raise ValueError("AI 返回格式错误")

        # 二次校验（双重保险）：检查是否真的重复了
        if word in history:
            print(f"⚠️ AI 竟然生成了重复词 {word}，正在重试...")
            return init_game()  # 递归重试

        return jsonify({
            "word_length": len(word),
            "clue": clue,
            # ⚠️ 安全提示：在生产环境中，这里不应该返回 "answer"。
            # 应该在后端 Session 中存储 answer，前端只传 guess，后端比对。
            # 为了本教程的简单可运行性，我们暂时返回，但在面试时请务必说明这一点！
            "debug_answer": word
        })

    except Exception as e:
        print(f"❌ 生成失败：{e}")
        return jsonify({"error": "AI 出题失败，请刷新重试"}), 500


@app.route('/api/check_char', methods=['POST'])
def check_char():
    """判断字符是否存在"""
    data = request.json
    user_char = data.get('char')
    target_word = data.get('answer')  # 实际应从 Session 获取
    clue = data.get('clue')

    if not user_char or len(user_char) != 1:
        return jsonify({"error": "请输入单个字符"}), 400

    all_text = target_word + clue
    is_found = user_char in all_text

    # 返回位置信息用于前端高亮
    locations = []
    for i, char in enumerate(target_word):
        if char == user_char:
            locations.append({"type": "word", "index": i})
    for i, char in enumerate(clue):
        if char == user_char:
            locations.append({"type": "clue", "index": i})

    return jsonify({
        "is_found": is_found,
        "locations": locations
    })


@app.route('/api/finish_game', methods=['POST'])
def finish_game():
    data = request.json
    username = data.get('username')
    if not username:
        return jsonify({"error": "未登录"}), 401

    word = data.get('word')
    clue = data.get('clue')
    attempts = data.get('attempts', 0)
    hints = data.get('hints', 0)

    if save_game_result(username, word, clue, attempts, hints):
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "duplicate"}), 400


try:
    init_db()
    print("✅ 数据库已初始化完成 (Users & GameHistory tables created)")
except Exception as e:
    # 如果初始化失败，打印详细错误，但不要阻止应用启动（防止死循环）
    print(f"❌ 数据库初始化失败：{e}")
    import traceback
    traceback.print_exc()

# ==========================================
# 本地开发入口 (仅在直接运行 python app.py 时生效)
# ==========================================
if __name__ == '__main__':
    import os

    # 获取 Render 分配的端口，如果没有则默认为 5000
    port = int(os.environ.get("PORT", 5000))

    # 启动 Flask 内置服务器 (仅用于本地调试)
    # 生产环境 Render 会使用上面的 init_db() + Gunicorn (由 Procfile 指定)
    app.run(host='0.0.0.0', port=port, debug=False)
