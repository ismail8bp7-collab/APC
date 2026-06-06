import sqlite3
import pandas as pd

conn = sqlite3.connect("plc_agg_5min.db")
df = pd.read_sql_query("SELECT * FROM plc_agg_5min ORDER BY id DESC", conn)

print(df.head(20))
conn.close()