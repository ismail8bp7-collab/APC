import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# Exemple de données
df = pd.DataFrame({
    "shift_time": ["13:05", "13:10", "13:15", "13:20", "13:25"],
    "rejet_predit": [0.42, 0.55, 0.31, 0.68, 0.47]
})

st.title("Historique des rejets prédits")

st.dataframe(df)

fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(df["shift_time"], df["rejet_predit"])
ax.set_xlabel("Shift 5 min")
ax.set_ylabel("Rejet prédit")
ax.set_title("Rejets prédits par shift")
ax.grid(axis="y")

st.pyplot(fig)