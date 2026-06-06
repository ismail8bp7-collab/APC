import os
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh


# =====================================================
# CONFIG PAGE
# =====================================================

st.set_page_config(
    page_title="APC CIL - Prédiction des rejets",
   
    layout="wide",
    initial_sidebar_state="expanded"
)

# Rafraîchissement automatique chaque 1 seconde
st_autorefresh(interval=1000, key="time_refresh")


# =====================================================
# CONFIG FILES
# =====================================================

PLC_AGG_DB = "plc_agg_5min.db"
PLC_AGG_TABLE = "plc_agg_5min"
LB_FILE = "DATASETwithoutPLC2.xlsx"


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

    [data-testid="stMetric"] {
        background: linear-gradient(180deg, rgba(255,255,255,0.13), rgba(255,255,255,0.07));
        border: 1px solid rgba(255,255,255,0.16);
        border-radius: 18px;
        padding: 18px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.20);
        min-height: 125px;
    }

    [data-testid="stMetricLabel"] {
        color: #d9ecff !important;
        font-weight: 700;
        font-size: 15px !important;
    }

    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-weight: 800;
        font-size: 34px !important;
        line-height: 1.15;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
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

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True
)


# =====================================================
# DATA SIMULATION
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
        "Timestamp": times,
        "Rejet prédit": values
    })


def create_plc_table():
    return pd.DataFrame({
        "Variable": [
            "R1_PH_mean_DPLUS1",
            "R1_PH_std_DPLUS1",
            "R1_TCCY_mean_DPLUS1",
            "R1_TCCY_std_DPLUS1",
            "R7_TOX_mean_DPLUS1",
            "R7_TOX_std_DPLUS1",
            "R7_PH_mean_DPLUS1",
            "R7_PH_std_DPLUS1"
        ],
        "Mean": [8.23, 0.18, 58.70, 4.35, 0.116, 0.028, 7.92, 0.07],
        "Std": [0.18, 0.02, 4.35, 0.31, 0.028, 0.006, 0.21, 0.04],
        "Unité": ["pH", "pH", "ppm", "ppm", "mg/L", "mg/L", "pH", "pH"]
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
# LOAD REAL DATA IF EXISTS
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

    except Exception:
        return None


def load_labo_blending_excel():
    if not os.path.exists(LB_FILE):
        return None

    try:
        df = pd.read_excel(LB_FILE)
        if df.empty:
            return None
        return df.head(12)

    except Exception:
        return None


def convert_last_plc_row_to_table(df_db):
    if df_db is None or df_db.empty:
        return create_plc_table()

    last = df_db.iloc[0].to_dict()
    rows = []

    for col, val in last.items():
        if col not in ["id", "window_start", "window_end"]:
            unit = "-"

            if "PH" in col.upper():
                unit = "pH"
            elif "TCCY" in col.upper():
                unit = "ppm"
            elif "TOX" in col.upper():
                unit = "mg/L"

            try:
                value = round(float(val), 4)
            except Exception:
                value = None

            rows.append({
                "Variable": col + "_DPLUS1",
                "Mean": value,
                "Std": "-",
                "Unité": unit
            })

    return pd.DataFrame(rows)


# =====================================================
# CHART FUNCTIONS
# =====================================================

def make_bar_chart(df):
    colors = ["#0ea5e9"] * len(df)
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
        range=[0, 1.05],
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
        range=[0, 1.1],
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
# DATA
# =====================================================

prediction_history = create_prediction_history()

plc_db_data = load_plc_agg_db()
plc_table = convert_last_plc_row_to_table(plc_db_data)
plc_mode = "Simulation" if plc_db_data is None else "Base réelle"

labo_real = load_labo_blending_excel()

if labo_real is None:
    labo_table = create_labo_blending_table()
    labo_mode = "Simulation"
else:
    labo_table = labo_real
    labo_mode = "Excel réel"

importance_df = create_importance_table()

current_prediction = float(prediction_history["Rejet prédit"].iloc[-1])
last_shift = "11:05–11:10"


# =====================================================
# SIDEBAR
# =====================================================

st.sidebar.title("APC CIL")
st.sidebar.caption("GOLD PROCESSING")

st.sidebar.markdown("---")

page = st.sidebar.radio(
    "NAVIGATION",
    [
        "Vue générale",
        "Données PLC",
        "Blending & Labo",
        "Prédiction",
        "Historique",
        "Paramètres"
    ]
)

st.sidebar.markdown("---")
st.sidebar.subheader("CONNEXIONS")
st.sidebar.success("OPC UA : Simulation")
st.sidebar.success(f"Base de données : {plc_mode}")
st.sidebar.success(f"Labo/Blending : {labo_mode}")
st.sidebar.success("Modèle ML : Prêt")

st.sidebar.markdown("---")
st.sidebar.caption("Utilisateur : Ingénieur Procédé")


# =====================================================
# HEADER
# =====================================================

now_time = datetime.now().strftime("%H:%M:%S")
now_date = datetime.now().strftime("%d/%m/%Y")

top1, top2 = st.columns([2.4, 2.6])

with top1:
    st.title("Plateforme de prédiction des rejets – APC CIL")
    st.caption("Supervision, agrégation PLC, prédiction ML et aide à la décision")

with top2:
    h1, h2, h3, h4 = st.columns([1.1, 0.9, 1.1, 1.1])

    with h1:
        st.success("🟢 Temps réel")

    with h2:
        st.info("ML prêt")

    with h3:
        st.info("↻ Sync 5 min")

    with h4:
        st.metric("🕒 Temps", now_time)
        st.caption(now_date)

st.divider()


# =====================================================
# PAGE VUE GÉNÉRALE
# =====================================================

if page == "Vue générale":

    k1, k2, k3, k4, k5 = st.columns(5)

    with k1:
        st.metric("Rejet prédit actuel", f"{current_prediction:.3f} g/t")

    with k2:
        st.metric("Modèle actif", "Gradient Boosting")

    with k3:
        st.metric("Dernier shift", last_shift)

    with k4:
        st.metric("Statut OPC UA", "Connecté")

    with k5:
        st.metric("Qualité données", "OK")

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

    t1, t2 = st.columns([1.65, 1.0])

    with t1:
        with st.container(border=True):
            st.subheader("Données Blending + Labo utilisées")
            st.dataframe(labo_table.head(12), use_container_width=True, height=430)
            st.caption("Données synchronisées toutes les 5 minutes")

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

    a, b, c = st.columns(3)

    with a:
        st.metric("Rejet prédit actuel", f"{current_prediction:.3f} g/t")

    with b:
        st.metric("Modèle actif", "Gradient Boosting")

    with c:
        st.metric("Dernier shift", last_shift)

    if current_prediction < 0.6:
        st.success("Statut : rejet attendu faible / modéré")
    elif current_prediction < 1.0:
        st.warning("Statut : rejet à surveiller")
    else:
        st.error("Statut : rejet élevé")


elif page == "Historique":
    st.title("Historique des prédictions")
    st.dataframe(prediction_history, use_container_width=True)
    st.plotly_chart(make_bar_chart(prediction_history), use_container_width=True)


elif page == "Paramètres":
    st.title("Paramètres système")

    st.code(f"""
PLC_AGG_DB = {PLC_AGG_DB}
PLC_AGG_TABLE = {PLC_AGG_TABLE}
LB_FILE = {LB_FILE}

MODE = Simulation sans PLC
WINDOW = 5 minutes
MODEL = Gradient Boosting
    """)