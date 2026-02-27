import sqlite3
import pandas as pd
from datetime import datetime

# 配置
DB_PATH = 'game_history.db'
EXPORT_FILE = 'game_data.xlsx'


def connect_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except Exception as e:
        print(f"❌ 连接数据库失败：{e}")
        return None


def print_section(title):
    print("\n" + "=" * 60)
    print(f"📊 {title}")
    print("=" * 60)


def main():
    conn = connect_db()
    if not conn:
        return

    cursor = conn.cursor()

    # 1. 检查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    if not any(t[0] == 'game_history' for t in tables):
        print("❌ 未找到 game_history 表，请确认数据库文件或先玩一局游戏。")
        return

    # 2. 查看最新 10 条记录
    print_section("🕒 最近 10 局游戏记录")
    query_recent = """
                   SELECT id, username, target_word, attempts, hints, created_at
                   FROM game_history
                   ORDER BY created_at DESC LIMIT 10 \
                   """
    df_recent = pd.read_sql_query(query_recent, conn)
    if not df_recent.empty:
        # 格式化时间列以便打印美观
        df_recent['created_at'] = pd.to_datetime(df_recent['created_at']).dt.strftime('%m-%d %H:%M')
        print(df_recent.to_string(index=False))
    else:
        print("暂无数据。")

    # 3. 用户活跃度排行 (按总局数)
    print_section("🏆 用户活跃度排行榜 (总局数)")
    query_active = """
                   SELECT username, COUNT(*) as total_games, SUM(attempts) as total_attempts
                   FROM game_history
                   GROUP BY username
                   ORDER BY total_games DESC LIMIT 10 \
                   """
    df_active = pd.read_sql_query(query_active, conn)
    if not df_active.empty:
        print(df_active.to_string(index=False))
    else:
        print("暂无数据。")

    # 4. 用户实力排行 (按平均猜测次数，越低越强)
    print_section("🎯 用户实力排行榜 (平均猜测次数越低越强)")
    query_skill = """
                  SELECT username, \
                         COUNT(*)                as games, \
                         ROUND(AVG(attempts), 2) as avg_attempts, \
                         ROUND(AVG(hints), 2)    as avg_hints
                  FROM game_history
                  GROUP BY username
                  HAVING games >= 2 -- 至少玩过 2 局才上榜
                  ORDER BY avg_attempts ASC LIMIT 10 \
                  """
    df_skill = pd.read_sql_query(query_skill, conn)
    if not df_skill.empty:
        print(df_skill.to_string(index=False))
    else:
        print("数据不足，需用户至少玩 2 局才能上榜。")

    # 5. 最难猜的词汇 Top 5
    print_section("🤯 最难猜的词汇 Top 5 (平均猜测次数最高)")
    query_hard = """
                 SELECT target_word, COUNT(*) as times_played, ROUND(AVG(attempts), 2) as avg_attempts
                 FROM game_history
                 GROUP BY target_word
                 HAVING times_played >= 2
                 ORDER BY avg_attempts DESC LIMIT 5 \
                 """
    df_hard = pd.read_sql_query(query_hard, conn)
    if not df_hard.empty:
        print(df_hard.to_string(index=False))
    else:
        print("数据不足，需词汇被玩过 2 次以上才能统计。")

    # 6. 导出所有数据到 Excel
    print_section(f"💾 导出数据到 {EXPORT_FILE}")
    try:
        query_all = "SELECT * FROM game_history ORDER BY created_at DESC"
        df_all = pd.read_sql_query(query_all, conn)

        if not df_all.empty:
            # 转换时间格式以便 Excel 读取
            df_all['created_at'] = pd.to_datetime(df_all['created_at'])

            # 导出
            df_all.to_excel(EXPORT_FILE, index=False)
            print(f"✅ 成功导出 {len(df_all)} 条数据到 '{EXPORT_FILE}'")
            print(f"   文件位置：{conn.execute('PRAGMA database_list').fetchone()[2]}/{EXPORT_FILE}")
        else:
            print("暂无数据可导出。")
    except Exception as e:
        print(f"❌ 导出失败：{e}")
        print("   提示：请确保安装了 openpyxl 库 (pip install openpyxl)")

    conn.close()
    print("\n" + "=" * 60)
    print("🔍 查询结束")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    # 检查依赖
    try:
        import pandas
    except ImportError:
        print("❌ 缺少 pandas 库，正在尝试安装...")
        import subprocess

        subprocess.check_call(["pip", "install", "pandas", "openpyxl"])
        print("✅ 安装完成，请重新运行脚本。")
        exit()

    try:
        import openpyxl
    except ImportError:
        print("❌ 缺少 openpyxl 库 (用于导出 Excel)，正在尝试安装...")
        import subprocess

        subprocess.check_call(["pip", "install", "openpyxl"])
        print("✅ 安装完成，请重新运行脚本。")
        exit()

    main()