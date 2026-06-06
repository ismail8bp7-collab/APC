import os
import sqlite3
from datetime import datetime, timedelta
from itertools import product
from textwrap import dedent

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh

try:
    import joblib
except Exception:
    joblib = None


# =====================================================
# CONFIG PAGE
# =====================================================

st.set_page_config(
    page_title="APC CIL - Prédiction des rejets",
    
    layout="wide",
    initial_sidebar_state="expanded"
)

# Refresh automatique dashboard
st_autorefresh(interval=5000, key="dashboard_refresh")


# =====================================================
# CONFIG FILES
# =====================================================

PLC_RAW_DB = "plc_data.db"
PLC_RAW_TABLE = "plc_readings"
MAX_RAW_DELAY_SECONDS = 5

PLC_AGG_DB = "plc_agg_5min.db"
PLC_AGG_TABLE = "plc_agg_5min"

PRED_DB = "predictions.db"
PRED_TABLE = "predictions"

LB_FILE = "DATASETwithoutPLC2.xlsx"

MODEL_FILE = "best_model.pkl"
COLS_FILE = "model_columns.pkl"

EMSI_LOGO = "emsi_logo.png"
MANA_LOGO = "mana_logo.png"

# Seuils / plages provisoires à valider avec le procédé
REJET_WARN_THRESHOLD = 0.60
REJET_HIGH_THRESHOLD = 1.00

WHAT_IF_SEARCH_SPACE = {
    "pH": {
        "values": [10.5, 10.6, 10.7, 10.8, 10.9, 11.0],
        "unit": "pH",
        "target": 10.7,
        "columns": ["R1_PH_mean_DPLUS1", "R7_PH_mean_DPLUS1"],
    },
    "TCCY": {
        "values": [400, 450, 500, 550, 600],
        "unit": "ppm",
        "target": 500,
        "columns": ["R1_TCCY_mean_DPLUS1", "R2_TCCY_mean_DPLUS1", "R6_TCCY_mean_DPLUS1"],
    },
    "TOX": {
        "values": [8, 9, 10, 11, 12],
        "unit": "mg/L",
        "target": 10,
        "columns": ["R1_TOX_mean_DPLUS1", "R7_TOX_mean_DPLUS1"],
    },
}

# Plages opératoires provisoires pour l'aide à la décision.
# À valider avec l'équipe procédé avant toute utilisation industrielle.
PLC_RECOMMENDATION_RULES = {
    "R1_PH": {
        "min": 10.5,
        "max": 11.0,
        "target": 10.7,
        "unit": "pH",
        "action_low": "Vérifier le dosage de chaux et ramener le pH vers la plage cible.",
        "action_high": "Réduire progressivement la correction pH si la limite haute est confirmée.",
        "action_ok": "Maintenir la régulation pH et poursuivre la surveillance."
    },
    "R1_TCCY": {
        "min": 400,
        "max": 600,
        "target": 500,
        "unit": "ppm",
        "action_low": "Vérifier le dosage cyanure et la disponibilité de la solution cyanurée.",
        "action_high": "Vérifier les limites opératoires et éviter un surdosage cyanure.",
        "action_ok": "Maintenir la consigne cyanure et suivre la tendance."
    },
    "R1_TOX": {
        "min": 8,
        "max": 12,
        "target": 10,
        "unit": "mg/L",
        "action_low": "Vérifier l’oxygénation et l’apport d’air/oxygène au réacteur.",
        "action_high": "Surveiller la stabilité de l’oxygénation et les conditions de brassage.",
        "action_ok": "Maintenir l’oxygénation actuelle et poursuivre la surveillance."
    },
    "R2_TCCY": {
        "min": 400,
        "max": 600,
        "target": 500,
        "unit": "ppm",
        "action_low": "Vérifier la continuité du dosage cyanure et la propagation dans le circuit.",
        "action_high": "Surveiller la concentration cyanure et respecter les limites validées.",
        "action_ok": "Maintenir la concentration cyanure et suivre la tendance."
    },
    "R6_TCCY": {
        "min": 400,
        "max": 600,
        "target": 500,
        "unit": "ppm",
        "action_low": "Vérifier la concentration cyanure en aval et l’efficacité de la lixiviation.",
        "action_high": "Vérifier les limites opératoires cyanure en aval du circuit.",
        "action_ok": "Maintenir les conditions cyanure et poursuivre le suivi."
    },
    "R7_PH": {
        "min": 10.5,
        "max": 11.0,
        "target": 10.7,
        "unit": "pH",
        "action_low": "Vérifier la stabilité du pH en fin de circuit et la correction alcaline.",
        "action_high": "Surveiller la limite haute du pH en fin de circuit.",
        "action_ok": "Maintenir la régulation pH en fin de circuit."
    },
    "R7_TOX": {
        "min": 8,
        "max": 12,
        "target": 10,
        "unit": "mg/L",
        "action_low": "Vérifier l’oxygénation en fin de circuit et l’apport d’air/oxygène.",
        "action_high": "Surveiller l’oxygénation et la stabilité du réacteur.",
        "action_ok": "Maintenir l’oxygénation actuelle et poursuivre la surveillance."
    },
}



# =====================================================
# HTML HELPER
# =====================================================

def render_html(code: str):
    st.markdown(dedent(code).strip(), unsafe_allow_html=True)


# =====================================================
# STYLE GLOBAL
# =====================================================

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(135deg, #061826 0%, #08253a 45%, #0b3552 100%);
        color: #eaf4ff;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #031827 0%, #052840 100%);
        border-right: 1px solid rgba(255,255,255,0.12);
    }

    [data-testid="stSidebar"] * {
        color: white !important;
    }

    [data-testid="stSidebarContent"] {
        padding-top: 1.2rem;
    }

    [data-testid="stHeader"] {
        background: transparent !important;
    }

    .block-container {
        padding-top: 1.2rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 100%;
    }

    h1, h2, h3, h4, h5, h6, p, label {
        color: #eaf4ff !important;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.14);
        border-radius: 18px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.18);
    }

    [data-testid="stDataFrame"] {
        border-radius: 14px;
        overflow: hidden;
    }

    .stAlert {
        background: linear-gradient(180deg, rgba(255,255,255,0.13), rgba(255,255,255,0.07)) !important;
        border: 1px solid rgba(255,255,255,0.16) !important;
        border-radius: 16px !important;
        color: #eaf4ff !important;
        box-shadow: 0 10px 25px rgba(0,0,0,0.18);
    }

    .stAlert p {
        color: #eaf4ff !important;
        font-weight: 700 !important;
    }

    /* ================= KPI CUSTOM CARDS ================= */

    .kpi-card {
        background: linear-gradient(180deg, rgba(255,255,255,0.13), rgba(255,255,255,0.07));
        border: 1px solid rgba(255,255,255,0.16);
        border-radius: 18px;
        padding: 20px 22px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.20);
        min-height: 125px;
    }

    .kpi-label {
        color: #d9ecff;
        font-size: 15px;
        font-weight: 750;
        margin-bottom: 12px;
    }

    .kpi-value {
        font-size: 34px;
        font-weight: 900;
        line-height: 1.15;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .kpi-yellow {
        color: #facc15;
    }

    .kpi-white {
        color: #ffffff;
    }

    .kpi-green {
        color: #22c55e;
    }

    .kpi-red {
        color: #ef4444;
    }

    .kpi-sub {
        color: #9fc4dc;
        font-size: 12px;
        margin-top: 8px;
    }

    .decision-card {
        background: linear-gradient(180deg, rgba(255,255,255,0.12), rgba(255,255,255,0.06));
        border: 1px solid rgba(255,255,255,0.16);
        border-radius: 18px;
        padding: 18px 20px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.18);
    }

    .decision-title {
        color: #ffffff;
        font-size: 20px;
        font-weight: 850;
        margin-bottom: 8px;
    }

    .decision-text {
        color: #d9ecff;
        font-size: 14px;
        line-height: 1.5;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True
)


# =====================================================
# DATA SIMULATION FALLBACK
# =====================================================

def create_prediction_history():
    now = datetime.now().replace(second=0, microsecond=0)
    times = [now - timedelta(minutes=5 * i) for i in range(11, -1, -1)]

    values = [
        0.41, 0.46, 0.52, 0.49, 0.55, 0.48,
        0.51, 0.44, 0.59, 0.62, 0.50, 0.47
    ]

    return pd.DataFrame({
        "Heure": [t.strftime("%H:%M") for t in times],
        "Rejet prédit": values
    })


def create_plc_table():
    return pd.DataFrame({
        "Variable": [
            "R1_PH",
            "R1_TCCY",
            "R1_TOX",
            "R2_TCCY",
            "R6_TCCY",
            "R7_PH",
            "R7_TOX"
        ],
        "Mean": [8.23, 58.70, 0.116, 55.2, 60.1, 7.92, 0.028],
        "Std": [0.18, 4.35, 0.028, 3.2, 3.7, 0.21, 0.006],
        "Unité": ["pH", "ppm", "mg/L", "ppm", "ppm", "pH", "mg/L"]
    })


def create_labo_blending_table():
    return pd.DataFrame({
        "Heure": ["11:10", "11:05", "11:00", "10:55", "10:50"],
        "Grade_wavg": [1.42, 1.45, 1.41, 1.39, 1.38],
        "HG_share": [18.7, 18.5, 18.2, 18.9, 18.4],
        "MG_share": [46.3, 45.9, 46.6, 45.1, 46.1],
        "LG_share": [35.0, 35.6, 35.2, 36.0, 35.5],
        "R2_SOLIDE_AU": [1.35, 1.32, 1.34, 1.33, 1.31],
        "R3_SOLIDE_AU": [1.48, 1.50, 1.47, 1.46, 1.44],
        "R4_SOLIDE_AU": [1.22, 1.24, 1.21, 1.20, 1.19],
    })


def create_importance_table():
    return pd.DataFrame({
        "Variable": [
            "R3_SOLIDE_AU",
            "R2_SOLIDE_AU",
            "R1_SOLIDE_AU",
            "R4_SOLIDE_AU",
            "R7_TOX_mean_DPLUS1"
        ],
        "Importance": [0.34, 0.23, 0.16, 0.10, 0.08]
    })


# =====================================================
# OPC UA STATUS FROM RAW PLC DB
# =====================================================

def is_opc_connected_from_raw_db():
    """
    Vérifie si OPC UA est connecté à partir de plc_data.db.
    Si la dernière ligne brute est récente, on considère OPC UA connecté.
    """

    if not os.path.exists(PLC_RAW_DB):
        return False

    try:
        conn = sqlite3.connect(PLC_RAW_DB)

        df = pd.read_sql_query(
            f"""
            SELECT *
            FROM {PLC_RAW_TABLE}
            ORDER BY id DESC
            LIMIT 1
            """,
            conn
        )

        conn.close()

        if df.empty:
            return False

        possible_time_cols = [
            "timestamp",
            "Timestamp",
            "time",
            "Time",
            "datetime",
            "Datetime",
            "date_time",
            "created_at",
            "TIME",
            "SHIFT_DATETIME"
        ]

        time_col = None

        for col in possible_time_cols:
            if col in df.columns:
                time_col = col
                break

        if time_col is None:
            print("Aucune colonne temps trouvée dans plc_data.db")
            print("Colonnes trouvées :", list(df.columns))
            return False

        last_time = pd.to_datetime(df[time_col].iloc[0], errors="coerce")

        if pd.isna(last_time):
            return False

        delay_seconds = (datetime.now() - last_time).total_seconds()

        return delay_seconds <= MAX_RAW_DELAY_SECONDS

    except Exception as e:
        print("Erreur vérification OPC UA depuis plc_data.db :", e)
        return False


# =====================================================
# LOAD PLC AGG DATA
# =====================================================

def load_plc_agg_db():
    if not os.path.exists(PLC_AGG_DB):
        return None

    try:
        conn = sqlite3.connect(PLC_AGG_DB)

        df = pd.read_sql_query(
            f"""
            SELECT *
            FROM {PLC_AGG_TABLE}
            ORDER BY id DESC
            LIMIT 20
            """,
            conn
        )

        conn.close()

        if df.empty:
            return None

        return df

    except Exception as e:
        print("Erreur lecture plc_agg_5min.db :", e)
        return None


def convert_last_plc_row_to_table(df_db):
    if df_db is None or df_db.empty:
        return create_plc_table()

    last = df_db.iloc[0].to_dict()

    grouped = {}

    for col, val in last.items():
        if col in ["id", "window_start", "window_end"]:
            continue

        try:
            value = round(float(val), 4)
        except Exception:
            value = None

        if col.endswith("_mean"):
            base_name = col.replace("_mean", "")

            if base_name not in grouped:
                grouped[base_name] = {
                    "Variable": base_name,
                    "Mean": "-",
                    "Std": "-",
                    "Unité": "-"
                }

            grouped[base_name]["Mean"] = value

        elif col.endswith("_std"):
            base_name = col.replace("_std", "")

            if base_name not in grouped:
                grouped[base_name] = {
                    "Variable": base_name,
                    "Mean": "-",
                    "Std": "-",
                    "Unité": "-"
                }

            grouped[base_name]["Std"] = value

        else:
            base_name = col

            if base_name not in grouped:
                grouped[base_name] = {
                    "Variable": base_name,
                    "Mean": value,
                    "Std": "-",
                    "Unité": "-"
                }

    for base_name in grouped:
        name_upper = base_name.upper()

        if "PH" in name_upper:
            grouped[base_name]["Unité"] = "pH"
        elif "TCCY" in name_upper:
            grouped[base_name]["Unité"] = "ppm"
        elif "TOX" in name_upper:
            grouped[base_name]["Unité"] = "mg/L"
        else:
            grouped[base_name]["Unité"] = "-"

    df_table = pd.DataFrame(list(grouped.values()))
    df_table = df_table[["Variable", "Mean", "Std", "Unité"]]

    return df_table


# =====================================================
# LOAD PREDICTION DATA
# =====================================================

def load_latest_prediction():
    if not os.path.exists(PRED_DB):
        return None

    try:
        conn = sqlite3.connect(PRED_DB)

        df = pd.read_sql_query(
            f"""
            SELECT *
            FROM {PRED_TABLE}
            ORDER BY id DESC
            LIMIT 1
            """,
            conn
        )

        conn.close()

        if df.empty:
            return None

        return df.iloc[0]

    except Exception as e:
        print("Erreur lecture predictions.db :", e)
        return None


def load_prediction_history():
    if not os.path.exists(PRED_DB):
        return create_prediction_history()

    try:
        conn = sqlite3.connect(PRED_DB)

        df = pd.read_sql_query(
            f"""
            SELECT *
            FROM {PRED_TABLE}
            ORDER BY id DESC
            LIMIT 12
            """,
            conn
        )

        conn.close()

        if df.empty:
            return create_prediction_history()

        df = df.sort_values("id").reset_index(drop=True)

        if "window_end" in df.columns:
            df["Heure"] = pd.to_datetime(df["window_end"], errors="coerce").dt.strftime("%H:%M")
        else:
            df["Heure"] = pd.to_datetime(df["timestamp"], errors="coerce").dt.strftime("%H:%M")

        df["Heure"] = df["Heure"].fillna("--:--")
        df["Rejet prédit"] = pd.to_numeric(df["prediction"], errors="coerce").fillna(0)

        return df[["Heure", "Rejet prédit"]]

    except Exception as e:
        print("Erreur lecture historique predictions.db :", e)
        return create_prediction_history()


# =====================================================
# LOAD LABO / BLENDING
# =====================================================

def load_labo_blending_excel():
    if not os.path.exists(LB_FILE):
        return None

    try:
        df = pd.read_excel(LB_FILE)

        if df.empty:
            return None

        return df.head(12)

    except Exception as e:
        print("Erreur lecture DATASETwithoutPLC2.xlsx :", e)
        return None


# =====================================================
# CHART FUNCTIONS
# =====================================================

def make_bar_chart(df):
    colors = ["#0ea5e9"] * len(df)

    if len(colors) > 0:
        colors[-1] = "#fb923c"

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df["Heure"],
        y=df["Rejet prédit"],
        marker_color=colors,
        text=[f"{v:.2f}" for v in df["Rejet prédit"]],
        textposition="outside",
        textfont=dict(color="#ffffff", size=13)
    ))

    max_y = max(1.05, float(df["Rejet prédit"].max()) + 0.2)

    fig.update_layout(
        height=360,
        margin=dict(l=20, r=20, t=20, b=50),
        plot_bgcolor="#08253a",
        paper_bgcolor="#08253a",
        font=dict(color="#eaf4ff", size=13),
        yaxis_title="g/t",
        showlegend=False,
        bargap=0.28
    )

    fig.update_yaxes(
        range=[0, max_y],
        gridcolor="rgba(255,255,255,0.15)",
        tickfont=dict(color="#eaf4ff")
    )

    fig.update_xaxes(
        tickfont=dict(color="#eaf4ff")
    )

    return fig


def make_line_chart(df):
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["Heure"],
        y=df["Rejet prédit"],
        mode="lines+markers",
        line=dict(color="#38bdf8", width=3),
        marker=dict(size=8, color="#fb923c")
    ))

    fig.add_hline(
        y=1.0,
        line_dash="dash",
        line_color="#fb923c",
        annotation_text="Seuil d’alerte (1.00 g/t)",
        annotation_position="top right",
        annotation_font_color="#fb923c"
    )

    max_y = max(1.1, float(df["Rejet prédit"].max()) + 0.2)

    fig.update_layout(
        height=360,
        margin=dict(l=20, r=20, t=20, b=50),
        plot_bgcolor="#08253a",
        paper_bgcolor="#08253a",
        font=dict(color="#eaf4ff", size=13),
        yaxis_title="g/t",
        showlegend=False
    )

    fig.update_yaxes(
        range=[0, max_y],
        gridcolor="rgba(255,255,255,0.15)",
        tickfont=dict(color="#eaf4ff")
    )

    fig.update_xaxes(
        tickfont=dict(color="#eaf4ff")
    )

    return fig 


def make_importance_chart(df):
    fig = px.bar(
        df.sort_values("Importance", ascending=True),
        x="Importance",
        y="Variable",
        orientation="h",
        text="Importance"
    )

    fig.update_layout(
        height=430,
        margin=dict(l=10, r=40, t=10, b=40),
        plot_bgcolor="#08253a",
        paper_bgcolor="#08253a",
        font=dict(color="#eaf4ff", size=12),
        xaxis_title="Importance (gain)",
        yaxis_title=""
    )

    fig.update_xaxes(
        gridcolor="rgba(255,255,255,0.15)",
        tickfont=dict(color="#eaf4ff")
    )

    fig.update_yaxes(
        tickfont=dict(color="#eaf4ff")
    )

    fig.update_traces(
        marker_color="#38bdf8",
        texttemplate="%{text:.2f}",
        textposition="outside",
        textfont=dict(color="#ffffff")
    )

    return fig


# =====================================================
# KPI CARD HELPER
# =====================================================

def kpi_card(label, value, value_class="kpi-white", sub=""):
    render_html(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value {value_class}">{value}</div>
        <div class="kpi-sub">{sub}</div>
    </div>
    """)



# =====================================================
# DECISION SUPPORT / WHAT-IF SIMULATION
# =====================================================

def load_model_assets():
    """
    Charge le modèle ML et les colonnes utilisées pendant l'entraînement.
    Si les fichiers ne sont pas disponibles, le module recommandation passe en mode règles simples.
    """
    if joblib is None:
        return None, None

    if not os.path.exists(MODEL_FILE) or not os.path.exists(COLS_FILE):
        return None, None

    try:
        model = joblib.load(MODEL_FILE)
        model_cols = joblib.load(COLS_FILE)
        return model, model_cols
    except Exception as e:
        print("Erreur chargement modèle ML :", e)
        return None, None


def build_current_ml_input(plc_db_data):
    """
    Reconstruit la même ligne d'entrée que le backend de prédiction :
    dernière ligne PLC agrégée + ligne labo/blending correspondante.
    """
    model, model_cols = load_model_assets()

    if model is None or model_cols is None:
        return None, None, None

    if plc_db_data is None or plc_db_data.empty:
        return None, model, model_cols

    if not os.path.exists(LB_FILE):
        return None, model, model_cols

    try:
        df_plc = plc_db_data.iloc[[0]].copy().reset_index(drop=True)
        plc_id = int(df_plc["id"].iloc[0]) if "id" in df_plc.columns else 1

        df_lb_all = pd.read_excel(LB_FILE)
        if df_lb_all.empty:
            return None, model, model_cols

        lb_index = (plc_id - 1) % len(df_lb_all)
        df_lb = df_lb_all.iloc[[lb_index]].reset_index(drop=True)

        plc_cols = [c for c in df_plc.columns if c not in ["id", "window_start", "window_end"]]
        df_plc = df_plc.rename(columns={c: f"{c}_DPLUS1" for c in plc_cols})

        df_input = pd.concat(
            [df_lb.reset_index(drop=True), df_plc.reset_index(drop=True)],
            axis=1
        )

        drop_cols = ["id", "window_start", "window_end"]
        target_cols = ["TARGET_REJET_JPLUS1", "REJET_FINAL_SOLIDE_AU"]

        df_input = df_input.drop(columns=[c for c in drop_cols if c in df_input.columns], errors="ignore")
        df_input = df_input.drop(columns=[c for c in target_cols if c in df_input.columns], errors="ignore")
        df_input = df_input.apply(pd.to_numeric, errors="coerce").fillna(0)
        df_input = df_input.reindex(columns=model_cols, fill_value=0)

        return df_input, model, model_cols

    except Exception as e:
        print("Erreur construction input ML pour what-if :", e)
        return None, model, model_cols


def run_what_if_simulation(df_current, model, model_cols):
    """
    Génère des scénarios virtuels sur pH, TCCY et TOX,
    puis sélectionne le scénario qui minimise le rejet prédit.
    """
    if df_current is None or model is None or model_cols is None:
        return None, None

    scenario_rows = []
    groups = list(WHAT_IF_SEARCH_SPACE.keys())
    values_list = [WHAT_IF_SEARCH_SPACE[g]["values"] for g in groups]

    try:
        for values in product(*values_list):
            scenario = df_current.copy()
            meta = {}

            for group_name, value in zip(groups, values):
                config = WHAT_IF_SEARCH_SPACE[group_name]
                meta[group_name] = value

                for col in config["columns"]:
                    if col in scenario.columns:
                        scenario[col] = value

            scenario_rows.append((scenario, meta))

        scenarios_df = pd.concat([s[0] for s in scenario_rows], ignore_index=True)
        scenarios_df = scenarios_df.reindex(columns=model_cols, fill_value=0)

        predictions = model.predict(scenarios_df)

        result_rows = []
        for i, (_, meta) in enumerate(scenario_rows):
            result_rows.append({
                "pH suggéré": meta.get("pH"),
                "TCCY suggéré": meta.get("TCCY"),
                "TOX suggéré": meta.get("TOX"),
                "Rejet simulé": float(predictions[i]),
            })

        result_df = pd.DataFrame(result_rows)
        result_df = result_df.sort_values("Rejet simulé", ascending=True).reset_index(drop=True)
        best_row = result_df.iloc[0] if not result_df.empty else None

        return result_df, best_row

    except Exception as e:
        print("Erreur simulation what-if :", e)
        return None, None


def get_risk_level(pred_value):
    if pred_value >= REJET_HIGH_THRESHOLD:
        return "Élevé", "kpi-red"
    elif pred_value >= REJET_WARN_THRESHOLD:
        return "Modéré", "kpi-yellow"
    else:
        return "Faible", "kpi-green"


def get_rule_for_plc_variable(variable_name):
    """
    Retourne les limites opératoires configurées pour une variable PLC.
    Si la variable exacte n'est pas trouvée, on applique une règle par type.
    """
    var = str(variable_name)

    if var in PLC_RECOMMENDATION_RULES:
        return PLC_RECOMMENDATION_RULES[var]

    var_upper = var.upper()

    if "PH" in var_upper:
        return {
            "min": 10.5,
            "max": 11.0,
            "target": 10.7,
            "unit": "pH",
            "action_low": "Vérifier la correction pH et ramener progressivement vers la plage cible.",
            "action_high": "Surveiller la limite haute du pH et corriger progressivement.",
            "action_ok": "Maintenir la régulation pH."
        }

    if "TCCY" in var_upper:
        return {
            "min": 400,
            "max": 600,
            "target": 500,
            "unit": "ppm",
            "action_low": "Vérifier le dosage cyanure.",
            "action_high": "Vérifier les limites opératoires cyanure.",
            "action_ok": "Maintenir la concentration cyanure."
        }

    if "TOX" in var_upper:
        return {
            "min": 8,
            "max": 12,
            "target": 10,
            "unit": "mg/L",
            "action_low": "Vérifier l’oxygénation du circuit CIL.",
            "action_high": "Surveiller la stabilité de l’oxygénation.",
            "action_ok": "Maintenir l’oxygénation actuelle."
        }

    return None


def get_plc_current_value(plc_table, variable_name):
    """
    Récupère la valeur moyenne actuelle d'une variable depuis le tableau PLC agrégé.
    """
    if plc_table is None or plc_table.empty:
        return None

    match = plc_table[plc_table["Variable"].astype(str) == str(variable_name)]

    if match.empty:
        return None

    try:
        return float(match.iloc[0]["Mean"])
    except Exception:
        return None


def evaluate_variable_state(value, rule):
    """
    Évalue l'état d'une variable par rapport à sa plage cible.
    """
    if value is None:
        return "Indisponible", "kpi-red", "Donnée indisponible : vérifier la communication ou l’agrégation."

    if value < rule["min"]:
        return "Bas", "kpi-yellow", rule["action_low"]

    if value > rule["max"]:
        return "Élevé", "kpi-red", rule["action_high"]

    return "OK", "kpi-green", rule["action_ok"]


def get_suggested_value(variable_name, current_value, rule, best_scenario):
    """
    Calcule la consigne suggérée pour chaque variable PLC.
    Si la simulation what-if est disponible, on utilise la meilleure valeur simulée
    selon le type de variable. Sinon, on utilise la cible définie dans les règles.
    """
    var_upper = str(variable_name).upper()

    if best_scenario is not None:
        try:
            if "PH" in var_upper and "pH suggéré" in best_scenario:
                return float(best_scenario["pH suggéré"])
            if "TCCY" in var_upper and "TCCY suggéré" in best_scenario:
                return float(best_scenario["TCCY suggéré"])
            if "TOX" in var_upper and "TOX suggéré" in best_scenario:
                return float(best_scenario["TOX suggéré"])
        except Exception:
            pass

    return float(rule["target"])


def build_plc_recommendation_table(plc_table, best_scenario):
    """
    Construit une table de recommandations pour toutes les entrées PLC suivies.
    Chaque variable possède sa valeur actuelle, sa plage cible, sa consigne suggérée,
    son état et une action opérateur.
    """
    rows = []

    for variable_name, rule in PLC_RECOMMENDATION_RULES.items():
        current_value = get_plc_current_value(plc_table, variable_name)
        state, state_color, action = evaluate_variable_state(current_value, rule)
        suggested_value = get_suggested_value(variable_name, current_value, rule, best_scenario)

        if current_value is None:
            current_display = "N/A"
        else:
            if rule["unit"] == "pH":
                current_display = f"{current_value:.2f}"
            elif rule["unit"] == "ppm":
                current_display = f"{current_value:.1f}"
            else:
                current_display = f"{current_value:.2f}"

        if rule["unit"] == "pH":
            suggested_display = f"{suggested_value:.1f}"
            target_display = f"{rule['min']:.1f}–{rule['max']:.1f}"
        elif rule["unit"] == "ppm":
            suggested_display = f"{suggested_value:.0f}"
            target_display = f"{rule['min']:.0f}–{rule['max']:.0f}"
        else:
            suggested_display = f"{suggested_value:.0f}"
            target_display = f"{rule['min']:.0f}–{rule['max']:.0f}"

        rows.append({
            "Variable": variable_name,
            "Valeur actuelle": current_display,
            "Plage cible": target_display,
            "Consigne suggérée": suggested_display,
            "État": state,
            "Unité": rule["unit"],
            "Action opérateur": action
        })

    return pd.DataFrame(rows)


def detect_process_issues(plc_table):
    """
    Détection des causes probables à partir de toutes les variables PLC configurées.
    """
    issues = []

    if plc_table is None or plc_table.empty:
        return ["Données PLC indisponibles : vérifier la communication et la base de données."]

    for variable_name, rule in PLC_RECOMMENDATION_RULES.items():
        current_value = get_plc_current_value(plc_table, variable_name)
        state, _, action = evaluate_variable_state(current_value, rule)

        if state == "Bas":
            issues.append(f"{variable_name} faible : {action}")
        elif state == "Élevé":
            issues.append(f"{variable_name} élevé : {action}")
        elif state == "Indisponible":
            issues.append(f"{variable_name} indisponible : vérifier la donnée PLC.")

    if not issues:
        issues.append("Aucune dérive critique détectée sur les entrées PLC configurées.")

    return issues


def build_recommendation_table(best_scenario, current_prediction, plc_table, data_quality_ok):
    risk_level, _ = get_risk_level(current_prediction)
    issues = detect_process_issues(plc_table)

    rows_df = build_plc_recommendation_table(
        plc_table=plc_table,
        best_scenario=best_scenario
    )

    if not data_quality_ok:
        global_message = "Qualité des données insuffisante : vérifier OPC UA, DB et prédiction avant décision."
    elif risk_level == "Élevé":
        global_message = "Risque élevé : intervention opérateur prioritaire recommandée."
    elif risk_level == "Modéré":
        global_message = "Risque modéré : surveiller les variables critiques et appliquer une correction progressive si nécessaire."
    else:
        global_message = "Risque faible : maintenir les conditions actuelles et poursuivre la surveillance."

    return rows_df, issues, risk_level, global_message



# =====================================================
# DATA
# =====================================================

prediction_history = load_prediction_history()
latest_prediction = load_latest_prediction()

plc_db_data = load_plc_agg_db()
plc_table = convert_last_plc_row_to_table(plc_db_data)

# Statut OPC UA basé sur plc_data.db temps réel
plc_connected = is_opc_connected_from_raw_db()

# Statut prédiction basé sur predictions.db
prediction_connected = latest_prediction is not None

# Qualité données
data_quality_ok = plc_connected and prediction_connected and not plc_table.empty

plc_mode = "Base réelle" if plc_db_data is not None else "Simulation"

labo_real = load_labo_blending_excel()

if labo_real is None:
    labo_table = create_labo_blending_table()
    labo_mode = "Simulation"
else:
    labo_table = labo_real
    labo_mode = "Excel réel"

importance_df = create_importance_table()

if latest_prediction is not None:
    current_prediction = float(latest_prediction["prediction"])

    ws = str(latest_prediction["window_start"])
    we = str(latest_prediction["window_end"])

    try:
        ws_short = pd.to_datetime(ws).strftime("%H:%M")
        we_short = pd.to_datetime(we).strftime("%H:%M")
        last_shift = f"{ws_short}–{we_short}"
    except Exception:
        last_shift = f"{ws} → {we}"

    prediction_mode = "Réel"
else:
    current_prediction = float(prediction_history["Rejet prédit"].iloc[-1])
    last_shift = "Simulation"
    prediction_mode = "Simulation"

opc_status_text = "Connecté" if plc_connected else "Déconnecté"
opc_status_color = "kpi-green" if plc_connected else "kpi-red"

quality_text = "Bon" if data_quality_ok else "Problème"
quality_color = "kpi-green" if data_quality_ok else "kpi-red"

# Module aide à la décision / consignes suggérées
ml_current_input, ml_model, ml_model_cols = build_current_ml_input(plc_db_data)
what_if_results, best_scenario = run_what_if_simulation(ml_current_input, ml_model, ml_model_cols)
recommendation_df, process_issues, risk_level, decision_message = build_recommendation_table(
    best_scenario=best_scenario,
    current_prediction=current_prediction,
    plc_table=plc_table,
    data_quality_ok=data_quality_ok
)
risk_text, risk_color = get_risk_level(current_prediction)


# =====================================================
# SIDEBAR
# =====================================================

st.sidebar.title("APC CIL")
st.sidebar.caption("GOLD PROCESSING")

st.sidebar.markdown("---")

page = st.sidebar.radio(
    "NAVIGATION",
    [
        "Overview",
        "Données PLC",
        "Blending & Labo",
        "Prédiction",
        "Aide à la décision",
        "Historique",
        "Paramètres"
    ]
)

st.sidebar.markdown("---")
st.sidebar.subheader("CONNEXIONS")

if plc_connected:
    st.sidebar.success("OPC UA : Connecté")
else:
    st.sidebar.error("OPC UA : Déconnecté")

if plc_db_data is not None:
    st.sidebar.success("Base de données : Base réelle")
else:
    st.sidebar.warning("Base de données : Simulation")

if labo_mode == "Excel réel":
    st.sidebar.success("Labo/Blending : Excel réel")
else:
    st.sidebar.warning("Labo/Blending : Simulation")

if prediction_connected:
    st.sidebar.success("Prédiction : Réel")
else:
    st.sidebar.warning("Prédiction : Simulation")

st.sidebar.success("Modèle ML : Prêt")

st.sidebar.markdown("---")
st.sidebar.caption("Utilisateur : Ingénieur Procédé")


# =====================================================
# HEADER
# =====================================================

now_time = datetime.now().strftime("%H:%M:%S")
now_date = datetime.now().strftime("%d/%m/%Y")

# Ligne 1 : Logo EMSI | Titre + sous-titre | Logo Mana Technology
header_left, header_center, header_right = st.columns([1.1, 3.8, 1.1])

with header_left:
    if os.path.exists(EMSI_LOGO):
        st.markdown("<div style='padding-top:22px;'>", unsafe_allow_html=True)
        st.image(EMSI_LOGO, width=190)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown("### EMSI")

with header_center:
    render_html("""
    <div style="text-align:center; padding-top:10px;">
        <div style="font-size:44px; font-weight:900; color:#eaf4ff; line-height:1.18;">
            Plateforme de prédiction des rejets – APC CIL
        </div>
        <div style="font-size:16px; color:#9fc4dc; margin-top:12px; font-weight:600;">
            Supervision, agrégation PLC, prédiction ML et aide à la décision
        </div>
    </div>
    """)

with header_right:
    if os.path.exists(MANA_LOGO):
        st.markdown("<div style='padding-top:26px; text-align:right;'>", unsafe_allow_html=True)
        st.image(MANA_LOGO, width=250)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown("### Mana Technology")

st.write("")

# Ligne 2 : badges système centrés sous le titre
spacer_left, badge1, badge2, badge3, time_box, spacer_right = st.columns([1.7, 0.95, 0.8, 0.95, 1.05, 1.7])

with badge1:
    if plc_connected:
        st.success("🟢 Temps réel")
    else:
        st.error("🔴 Hors ligne")

with badge2:
    st.info("ML prêt")

with badge3:
    st.info("↻ Sync 5 sec")

with time_box:
    st.metric("🕒 Temps", now_time)
    st.caption(now_date)

st.divider()


# =====================================================
# PAGE VUE GÉNÉRALE
# =====================================================

if page == "Overview":

    k1, k2, k3, k4, k5 = st.columns(5)

    with k1:
        kpi_card(
            label="Rejet prédit actuel",
            value=f"{current_prediction:.3f} g/t",
            value_class="kpi-yellow",
            sub="dernière prédiction ML"
        )

    with k2:
        kpi_card(
            label="Niveau de risque",
            value=risk_text,
            value_class=risk_color,
            sub="selon le rejet prédit"
        )

    with k3:
        kpi_card(
            label="Dernier shift",
            value=last_shift,
            value_class="kpi-white",
            sub="fenêtre 5 minutes"
        )

    with k4:
        kpi_card(
            label="Statut OPC UA",
            value=opc_status_text,
            value_class=opc_status_color,
            sub=f"délai max {MAX_RAW_DELAY_SECONDS}s"
        )

    with k5:
        kpi_card(
            label="Qualité données",
            value=quality_text,
            value_class=quality_color,
            sub="cohérence DB / prédiction"
        )

    st.write("")

    c1, c2, c3 = st.columns([1.25, 1.15, 1.05])

    with c1:
        with st.container(border=True):
            st.subheader("Historique des rejets prédits par shift (5 min)")
            st.plotly_chart(make_bar_chart(prediction_history), use_container_width=True)

    with c2:
        with st.container(border=True):
            st.subheader("Évolution des rejets prédits")
            st.plotly_chart(make_line_chart(prediction_history), use_container_width=True)

    with c3:
        with st.container(border=True):
            st.subheader("Variables PLC agrégées")
            st.dataframe(plc_table.head(8), use_container_width=True, height=360)

    st.write("")

    d1, d2 = st.columns([1.05, 1.15])

    with d1:
        with st.container(border=True):
            st.subheader("Aide à la décision opérateur")
            if risk_text == "Élevé":
                st.error(decision_message)
            elif risk_text == "Modéré":
                st.warning(decision_message)
            else:
                st.success(decision_message)

            st.markdown("**Causes probables / points à vérifier :**")
            for issue in process_issues[:5]:
                st.write(f"- {issue}")

            st.caption("Les recommandations sont indicatives et doivent être validées par l’opérateur.")

    with d2:
        with st.container(border=True):
            st.subheader("Consignes suggérées")
            st.dataframe(recommendation_df, use_container_width=True, height=360)

            if best_scenario is not None:
                st.metric("Meilleur rejet simulé", f"{best_scenario['Rejet simulé']:.3f} g/t")
            else:
                st.info("Mode règles simples : modèle ML ou fichiers .pkl non disponibles.")

    st.write("")

    t1, t2 = st.columns([1.65, 1.0])

    with t1:
        with st.container(border=True):
            st.subheader("Données Blending + Labo utilisées")
            st.dataframe(labo_table.head(12), use_container_width=True, height=430)
            st.caption("Données synchronisées avec la simulation Blending/Labo")

    with t2:
        with st.container(border=True):
            st.subheader("Top variables influentes")
            st.plotly_chart(make_importance_chart(importance_df), use_container_width=True)


# =====================================================
# OTHER PAGES
# =====================================================

elif page == "Données PLC":
    st.title("Données PLC agrégées")
    st.info(f"Mode actuel : {plc_mode}")

    if plc_db_data is not None:
        st.dataframe(plc_db_data, use_container_width=True)
    else:
        st.dataframe(plc_table, use_container_width=True)


elif page == "Blending & Labo":
    st.title("Blending & Labo")
    st.info(f"Mode actuel : {labo_mode}")
    st.dataframe(labo_table, use_container_width=True)


elif page == "Prédiction":
    st.title("Prédiction du rejet final")
    st.info(f"Mode actuel : {prediction_mode}")

    a, b, c = st.columns(3)

    with a:
        kpi_card(
            label="Rejet prédit actuel",
            value=f"{current_prediction:.3f} g/t",
            value_class="kpi-yellow",
            sub="dernière prédiction ML"
        )

    with b:
        kpi_card(
            label="Modèle actif",
            value="Gradient Boosting",
            value_class="kpi-white",
            sub="modèle opérationnel"
        )

    with c:
        kpi_card(
            label="Dernier shift",
            value=last_shift,
            value_class="kpi-white",
            sub="fenêtre 5 minutes"
        )

    if latest_prediction is not None:
        st.subheader("Dernière prédiction enregistrée")
        st.dataframe(pd.DataFrame([latest_prediction]), use_container_width=True)

    if current_prediction < 0.6:
        st.success("Statut : rejet attendu faible / modéré")
    elif current_prediction < 1.0:
        st.warning("Statut : rejet à surveiller")
    else:
        st.error("Statut : rejet élevé")



elif page == "Aide à la décision":
    st.title("Aide à la décision opérateur")
    st.caption("Recommandations et consignes suggérées à partir de l’état actuel du procédé et de scénarios simulés.")

    a, b, c, d = st.columns(4)

    with a:
        kpi_card(
            label="Rejet prédit actuel",
            value=f"{current_prediction:.3f} g/t",
            value_class="kpi-yellow",
            sub="dernière prédiction ML"
        )

    with b:
        kpi_card(
            label="Niveau de risque",
            value=risk_text,
            value_class=risk_color,
            sub="seuils configurables"
        )

    with c:
        if best_scenario is not None:
            best_value = f"{best_scenario['Rejet simulé']:.3f} g/t"
            best_sub = "meilleur scénario what-if"
        else:
            best_value = "N/A"
            best_sub = "modèle indisponible"

        kpi_card(
            label="Rejet simulé min.",
            value=best_value,
            value_class="kpi-green" if best_scenario is not None else "kpi-red",
            sub=best_sub
        )

    with d:
        kpi_card(
            label="Dernier shift",
            value=last_shift,
            value_class="kpi-white",
            sub="fenêtre de référence"
        )

    st.write("")

    col1, col2 = st.columns([1.0, 1.2])

    with col1:
        with st.container(border=True):
            st.subheader("Diagnostic opérateur")

            if risk_text == "Élevé":
                st.error(decision_message)
            elif risk_text == "Modéré":
                st.warning(decision_message)
            else:
                st.success(decision_message)

            st.markdown("**Causes probables / points à vérifier :**")
            for issue in process_issues:
                st.write(f"- {issue}")

            st.markdown("**Règle importante :**")
            st.info("La plateforme propose les consignes, mais ne modifie pas automatiquement le PLC. La décision finale reste chez l’opérateur.")

    with col2:
        with st.container(border=True):
            st.subheader("Consignes suggérées")
            st.dataframe(recommendation_df, use_container_width=True, height=360)

            if best_scenario is not None:
                st.success("Consignes calculées par simulation what-if avec le modèle ML.")
            else:
                st.warning("Consignes affichées en mode règles simples, car le modèle ML ou les fichiers .pkl ne sont pas disponibles.")

    st.write("")

    if what_if_results is not None:
        with st.container(border=True):
            st.subheader("Top scénarios simulés")
            st.caption("Chaque scénario modifie virtuellement les variables contrôlables pH, TCCY et TOX, puis le modèle ML estime le rejet correspondant.")
            st.dataframe(
                what_if_results.head(10).style.format({"Rejet simulé": "{:.3f}"}),
                use_container_width=True,
                height=360
            )
    else:
        with st.container(border=True):
            st.subheader("Simulation what-if")
            st.info("Pour activer la simulation ML, place best_model.pkl, model_columns.pkl et DATASETwithoutPLC2.xlsx dans le même dossier que app.py.")


elif page == "Historique":
    st.title("Historique des prédictions")
    st.dataframe(prediction_history, use_container_width=True)
    st.plotly_chart(make_bar_chart(prediction_history), use_container_width=True)


elif page == "Paramètres":
    st.title("Paramètres système")

    st.code(f"""
PLC_RAW_DB = {PLC_RAW_DB}
PLC_RAW_TABLE = {PLC_RAW_TABLE}
MAX_RAW_DELAY_SECONDS = {MAX_RAW_DELAY_SECONDS}

PLC_AGG_DB = {PLC_AGG_DB}
PLC_AGG_TABLE = {PLC_AGG_TABLE}

PRED_DB = {PRED_DB}
PRED_TABLE = {PRED_TABLE}

LB_FILE = {LB_FILE}

MODE PLC = {plc_mode}
MODE PREDICTION = {prediction_mode}

OPC UA STATUS = {opc_status_text}
DATA QUALITY = {quality_text}

REFRESH = 5 secondes
WINDOW = 5 minutes
MODEL = Gradient Boosting

REJET_WARN_THRESHOLD = {REJET_WARN_THRESHOLD}
REJET_HIGH_THRESHOLD = {REJET_HIGH_THRESHOLD}
WHAT_IF_MODE = {"Actif" if what_if_results is not None else "Règles simples"}
    """)