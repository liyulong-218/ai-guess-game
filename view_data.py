import sqlite3
import pandas as pd  # 需要安装: pip install pandas

# 连接数据库
conn = sqlite3.connect('game_history.db')

# 读取数据
# 方式 A: 直接打印
print("--- 最近的游戏记录 ---")
cursor = conn.execute("SELECT id, target_word, attempts, created_at FROM game_history ORDER BY id DESC LIMIT 10")
for row in cursor:
    print(f"ID: {row[0]}, 词: {row[1]}, 次数: {row[2]}, 时间: {row[3]}")

# 方式 B: 导出为 Excel (可选，需要安装 openpyxl: pip install openpyxl)
# df = pd.read_sql_query("SELECT * FROM game_history", conn)
# df.to_excel("game_data.xlsx", index=False)
# print("\n已导出为 game_data.xlsx")

conn.close()