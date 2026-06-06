import sqlite3
import pandas as pd

conn = sqlite3.connect("plc_data.db")

df = pd.read_sql_query("SELECT * FROM plc_readings", conn)

print(df.head(50))