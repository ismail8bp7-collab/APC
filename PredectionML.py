import sqlite3
import time
from datetime import datetime, timedelta

import pandas as pd
import joblib
from asyncua.sync import Client


# =====================================================
# CONFIG
# =====================================================

PLC_DB = "plc_agg_5min.db"
LB_FILE = "DATASETwithoutPLC2.xlsx"

MODEL_FILE = "best_model.pkl"
COLS_FILE = "model_columns.pkl"

ENDPOINT = "opc.tcp://192.168.11.53:4870"
PRED_NODE_ID = "ns=3;s=REJET_PREDIT"

WINDOW_MINUTES = 5
POST_BOUNDARY_DELAY_SECONDS = 10

PREDICTION_DB = "predictions.db"


# =====================================================
# TIME HELPERS
# =====================================================

def next_5min_boundary():
    """
    Retourne le prochain temps multiple de 5 minutes.
    Exemple :
    11:02:10 -> 11:05:00
    11:05:01 -> 11:10:00
    """
    now = datetime.now()
    minute = now.minute

    next_minute = ((minute // WINDOW_MINUTES) + 1) * WINDOW_MINUTES

    if next_minute >= 60:
        next_time = now.replace(
            minute=0,
            second=0,
            microsecond=0
        ) + timedelta(hours=1)
    else:
        next_time = now.replace(
            minute=next_minute,
            second=0,
            microsecond=0
        )

    return next_time


def wait_until(target_time):
    """
    Attend jusqu'au temps cible.
    """
    while True:
        now = datetime.now()
        remaining = (target_time - now).total_seconds()

        if remaining <= 0:
            break

        print(
            f"Attente prochaine fenêtre : {target_time.strftime('%H:%M:%S')} "
            f"| reste {remaining:.1f}s",
            end="\r"
        )

        time.sleep(min(1, remaining))

    print()


# =====================================================
# SAVE PREDICTION DB
# =====================================================

def save_prediction_to_db(plc_id, lb_index, window_start, window_end, pred_value):
    """
    Stocke chaque prédiction dans predictions.db
    pour que Streamlit puisse lire la dernière valeur réelle.
    """

    conn = sqlite3.connect(PREDICTION_DB)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        plc_agg_id INTEGER,
        lb_index INTEGER,
        window_start TEXT,
        window_end TEXT,
        prediction REAL
    )
    """)

    cursor.execute("""
    INSERT INTO predictions (
        timestamp,
        plc_agg_id,
        lb_index,
        window_start,
        window_end,
        prediction
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        int(plc_id),
        int(lb_index),
        str(window_start),
        str(window_end),
        float(pred_value)
    ))

    conn.commit()
    conn.close()

    print("Prédiction stockée dans predictions.db")


# =====================================================
# PREDICTION FUNCTION
# =====================================================

def run_prediction_once():
    print("\n" + "=" * 80)
    print("PRÉDICTION SHIFT 5 MIN :", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 80)

    # ================================
    # 1. Charger PLC agrégé dernière ligne
    # ================================

    conn = sqlite3.connect(PLC_DB)

    df_plc = pd.read_sql_query("""
    SELECT * FROM plc_agg_5min 
    ORDER BY id DESC 
    LIMIT 1
    """, conn)

    conn.close()

    if df_plc.empty:
        raise ValueError("La table plc_agg_5min est vide.")

    plc_id = int(df_plc["id"].iloc[0])

    window_start = df_plc["window_start"].iloc[0] if "window_start" in df_plc.columns else ""
    window_end = df_plc["window_end"].iloc[0] if "window_end" in df_plc.columns else ""

    print("\nDernier PLC agg id =", plc_id)
    print("Fenêtre PLC :", window_start, "→", window_end)

    # Renommer colonnes PLC pour matcher training
    plc_cols = [
        c for c in df_plc.columns
        if c not in ["id", "window_start", "window_end"]
    ]

    df_plc = df_plc.rename(columns={c: f"{c}_DPLUS1" for c in plc_cols})

    # ================================
    # 2. Charger LABO + BLENDING complet
    # ================================

    df_lb_all = pd.read_excel(LB_FILE)

    if df_lb_all.empty:
        raise ValueError(f"Le fichier {LB_FILE} est vide.")

    # Choix ligne LABO/BLENDING selon id PLC
    # id PLC commence à 1, index pandas commence à 0
    # Si on dépasse la dernière ligne, on revient à la première
    lb_index = (plc_id - 1) % len(df_lb_all)

    df_lb = df_lb_all.iloc[[lb_index]].reset_index(drop=True)

    print(f"Ligne LABO/BLENDING utilisée = {lb_index}")
    print("Nombre total lignes LABO/BLENDING =", len(df_lb_all))

    # ================================
    # 3. Fusionner LABO+BLENDING + PLC
    # ================================

    df_input = pd.concat(
        [
            df_lb.reset_index(drop=True),
            df_plc.reset_index(drop=True)
        ],
        axis=1
    )

    # ================================
    # 4. Nettoyage
    # ================================

    drop_cols = ["id", "window_start", "window_end"]

    df_input = df_input.drop(
        columns=[c for c in drop_cols if c in df_input.columns],
        errors="ignore"
    )

    target_cols = ["TARGET_REJET_JPLUS1", "REJET_FINAL_SOLIDE_AU"]

    df_input = df_input.drop(
        columns=[c for c in target_cols if c in df_input.columns],
        errors="ignore"
    )

    df_input = df_input.apply(pd.to_numeric, errors="coerce")
    df_input = df_input.fillna(0)

    # ================================
    # 5. Charger modèle
    # ================================

    model = joblib.load(MODEL_FILE)
    model_cols = joblib.load(COLS_FILE)

    df_input = df_input.reindex(columns=model_cols, fill_value=0)

    print("\nNombre colonnes input :", len(df_input.columns))
    print("Nombre colonnes modèle:", len(model_cols))

    # ================================
    # 6. Prédiction
    # ================================

    prediction = model.predict(df_input)
    pred_value = float(prediction[0])

    print("\nPRÉDICTION REJET =", pred_value)

    # ================================
    # 7. Écriture OPC UA
    # ================================

    try:
        with Client(ENDPOINT) as client:
            node = client.get_node(PRED_NODE_ID)
            node.write_value(pred_value)

        print("Valeur envoyée au PLC :", pred_value)

    except Exception as e:
        print("Erreur écriture OPC :", e)

    # ================================
    # 8. Stocker prédiction dans DB
    # ================================

    save_prediction_to_db(
        plc_id=plc_id,
        lb_index=lb_index,
        window_start=window_start,
        window_end=window_end,
        pred_value=pred_value
    )


# =====================================================
# LOOP SYNCHRONISÉE 5 MIN
# =====================================================

if __name__ == "__main__":
    print("Backend prédiction démarré.")
    print("Exécution synchronisée toutes les 5 minutes.")
    print(f"Délai sécurité après frontière = {POST_BOUNDARY_DELAY_SECONDS}s")

    while True:
        target_time = next_5min_boundary()

        wait_until(target_time)

        print(
            f"Attente sécurité {POST_BOUNDARY_DELAY_SECONDS}s "
            "pour laisser l'agrégation finir..."
        )

        time.sleep(POST_BOUNDARY_DELAY_SECONDS)

        try:
            run_prediction_once()
        except Exception as e:
            print("Erreur pendant la prédiction :", e)