import sqlite3
import time
from datetime import datetime

import pandas as pd


RAW_DB = "plc_data.db"
AGG_DB = "plc_agg_5min.db"

RAW_TABLE = "plc_readings"
AGG_TABLE = "plc_agg_5min"

WINDOW_MINUTES = 5


def create_agg_table(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {AGG_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            R1_PH_mean REAL,
            R1_PH_std REAL,
            R1_TCCY_mean REAL,
            R1_TCCY_std REAL,
            R1_TOX_mean REAL,
            R1_TOX_std REAL,
            R2_TCCY_mean REAL,
            R2_TCCY_std REAL,
            R6_TCCY_mean REAL,
            R6_TCCY_std REAL,
            R7_PH_mean REAL,
            R7_PH_std REAL,
            R7_TOX_mean REAL,
            R7_TOX_std REAL
        )
    """)
    conn.commit()


def get_last_aggregated_window_end(conn: sqlite3.Connection) -> str | None:
    query = f"SELECT MAX(window_end) AS last_end FROM {AGG_TABLE}"
    df = pd.read_sql_query(query, conn)
    if df.empty or pd.isna(df.loc[0, "last_end"]):
        return None
    return df.loc[0, "last_end"]


def load_raw_data_for_window(raw_conn: sqlite3.Connection, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> pd.DataFrame:
    query = f"""
        SELECT *
        FROM {RAW_TABLE}
        WHERE timestamp >= ? AND timestamp < ?
        ORDER BY timestamp
    """
    df = pd.read_sql_query(
        query,
        raw_conn,
        params=(start_ts.strftime("%Y-%m-%d %H:%M:%S"), end_ts.strftime("%Y-%m-%d %H:%M:%S"))
    )
    return df


def aggregate_window(df: pd.DataFrame, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> pd.DataFrame | None:
    if df.empty:
        return None

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    value_cols = [
        "R1_PH",
        "R1_TCCY",
        "R1_TOX",
        "R2_TCCY",
        "R6_TCCY",
        "R7_PH",
        "R7_TOX",
    ]

    for col in value_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    row = {
        "window_start": start_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "window_end": end_ts.strftime("%Y-%m-%d %H:%M:%S"),
    }

    for col in value_cols:
        if col in df.columns:
            row[f"{col}_mean"] = df[col].mean()
            row[f"{col}_std"] = df[col].std()
        else:
            row[f"{col}_mean"] = None
            row[f"{col}_std"] = None

    agg_df = pd.DataFrame([row])
    return agg_df


def insert_aggregated_row(agg_conn: sqlite3.Connection, agg_df: pd.DataFrame) -> None:
    agg_df.to_sql(AGG_TABLE, agg_conn, if_exists="append", index=False)


def get_first_raw_timestamp(raw_conn: sqlite3.Connection) -> pd.Timestamp | None:
    query = f"SELECT MIN(timestamp) AS first_ts FROM {RAW_TABLE}"
    df = pd.read_sql_query(query, raw_conn)
    if df.empty or pd.isna(df.loc[0, "first_ts"]):
        return None
    return pd.to_datetime(df.loc[0, "first_ts"], errors="coerce")


def floor_to_5min(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.floor(f"{WINDOW_MINUTES}min")


def run_aggregation_once() -> None:
    raw_conn = sqlite3.connect(RAW_DB)
    agg_conn = sqlite3.connect(AGG_DB)

    try:
        create_agg_table(agg_conn)

        last_end = get_last_aggregated_window_end(agg_conn)

        if last_end is None:
            first_ts = get_first_raw_timestamp(raw_conn)
            if first_ts is None:
                print("Aucune donnée brute trouvée dans plc_data.db")
                return
            current_start = floor_to_5min(first_ts)
        else:
            current_start = pd.to_datetime(last_end)

        now = pd.Timestamp.now().floor("s")
        current_end_limit = floor_to_5min(now)

        while current_start + pd.Timedelta(minutes=WINDOW_MINUTES) <= current_end_limit:
            current_end = current_start + pd.Timedelta(minutes=WINDOW_MINUTES)

            df_window = load_raw_data_for_window(raw_conn, current_start, current_end)
            agg_df = aggregate_window(df_window, current_start, current_end)

            print("\n======================================")
            print(f"Fenêtre : {current_start} -> {current_end}")
            print(f"Lignes brutes trouvées : {len(df_window)}")

            if agg_df is None:
                print("Aucune donnée pour cette fenêtre, rien à insérer.")
            else:
                insert_aggregated_row(agg_conn, agg_df)
                print(" Ligne agrégée insérée dans plc_agg_5min.db")
                print(agg_df.T)

            current_start = current_end

    finally:
        raw_conn.close()
        agg_conn.close()


def run_forever(poll_seconds: int = 10) -> None:
    print("Démarrage de l’agrégation 5 min...")
    while True:
        try:
            run_aggregation_once()
        except Exception as e:
            print(f"Erreur pendant l’agrégation : {e}")

        time.sleep(poll_seconds)


if __name__ == "__main__":
    run_forever(poll_seconds=10)