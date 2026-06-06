import sqlite3
import pandas as pd
import joblib
from asyncua.sync import Client

# ================================
# CONFIG
# ================================
PLC_DB = "plc_agg_5min.db"
LB_FILE = "DATASETwithoutPLC2.xlsx"

MODEL_FILE = "best_model.pkl"
COLS_FILE = "model_columns.pkl"

ENDPOINT = "opc.tcp://192.168.11.33:4870"
PRED_NODE_ID = "ns=3;s=REJET_PREDIT"


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
print("\nDernier PLC agg id =", plc_id)

# Renommer colonnes PLC pour matcher training
plc_cols = [c for c in df_plc.columns if c not in ["id", "window_start", "window_end"]]
df_plc = df_plc.rename(columns={c: f"{c}_DPLUS1" for c in plc_cols})


# ================================
# 2. Charger LABO + BLENDING complet
# ================================
df_lb_all = pd.read_excel(LB_FILE)

print("\n===== APERÇU DATASET WITHOUT PLC =====")
print("Shape:", df_lb_all.shape)
print(df_lb_all.head())

if df_lb_all.empty:
    raise ValueError(f"Le fichier {LB_FILE} est vide.")

# Choix ligne LABO/BLENDING selon id PLC
# id commence à 1, index pandas commence à 0
lb_index = (plc_id - 1) % len(df_lb_all)

df_lb = df_lb_all.iloc[[lb_index]].reset_index(drop=True)

print(f"\nLigne LABO/BLENDING utilisée = {lb_index}")
print(df_lb)


# ================================
# 3. Fusionner LABO+BLENDING + PLC
# ================================
df_input = pd.concat(
    [df_lb.reset_index(drop=True), df_plc.reset_index(drop=True)],
    axis=1
)


# ================================
# 4. Nettoyage
# ================================
drop_cols = ["id", "window_start", "window_end"]
df_input = df_input.drop(columns=[c for c in drop_cols if c in df_input.columns], errors="ignore")

target_cols = ["TARGET_REJET_JPLUS1", "REJET_FINAL_SOLIDE_AU"]
df_input = df_input.drop(columns=[c for c in target_cols if c in df_input.columns], errors="ignore")

df_input = df_input.apply(pd.to_numeric, errors="coerce")
df_input = df_input.fillna(0)


# ================================
# 5. Charger modèle
# ================================
model = joblib.load(MODEL_FILE)
model_cols = joblib.load(COLS_FILE)

df_input = df_input.reindex(columns=model_cols, fill_value=0)

print("\n===== INPUT FINAL ML =====")
print(df_input)

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