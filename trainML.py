import pandas as pd
import numpy as np
import joblib

from sklearn.impute import KNNImputer
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error


# =====================================================
# CONFIG
# =====================================================

FILE = "DATASET_FINAL_CIL_V5.xlsx"
TARGET = "TARGET_REJET_JPLUS1"
TEST_RATIO = 0.2


# =====================================================
# 1. LOAD DATA
# =====================================================

df = pd.read_excel(FILE)

print("Dataset initial :", df.shape)


# =====================================================
# 2. PREPARATION FINALE DU DATASET
# =====================================================

# Supprimer les lignes où la cible est manquante
df = df.dropna(subset=[TARGET])

# Séparation X / y
X = df.drop(columns=[TARGET], errors="ignore")
y = df[TARGET]

# Conversion des variables explicatives en numérique
X = X.apply(pd.to_numeric, errors="coerce")

# Supprimer les colonnes totalement vides
X = X.dropna(axis=1, how="all")

# Supprimer les variables avec plus de 80% de valeurs manquantes
missing_rate = X.isna().mean()
cols_to_drop = missing_rate[missing_rate > 0.80].index.tolist()

X = X.drop(columns=cols_to_drop)

print("Colonnes supprimées car NaN > 80% :", len(cols_to_drop))

# Imputation KNN pour remplir les valeurs manquantes restantes
nan_before = X.isna().sum().sum()

imputer = KNNImputer(n_neighbors=5, weights="distance")
X_imputed = imputer.fit_transform(X)

X = pd.DataFrame(X_imputed, columns=X.columns, index=X.index)

nan_after = X.isna().sum().sum()

print("NaN avant KNN :", nan_before)
print("NaN après KNN :", nan_after)
print("Nombre final de features :", X.shape[1])


# =====================================================
# 3. SPLIT CHRONOLOGIQUE TRAIN / TEST
# =====================================================

n = len(X)
split = int(n * (1 - TEST_RATIO))

X_train = X.iloc[:split]
X_test = X.iloc[split:]

y_train = y.iloc[:split]
y_test = y.iloc[split:]

print("Train :", X_train.shape)
print("Test  :", X_test.shape)


# =====================================================
# 4. MODELES MACHINE LEARNING
# =====================================================

models = {
    "Ridge": Ridge(),
    "RandomForest": RandomForestRegressor(
        n_estimators=300,
        random_state=42
    ),
    "GradientBoosting": GradientBoostingRegressor(
        n_estimators=300,
        random_state=42
    )
}
results = []

for name, model in models.items():
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    r2 = r2_score(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae = mean_absolute_error(y_test, y_pred)

    results.append({
        "Model": name,
        "R2": r2,
        "RMSE": rmse,
        "MAE": mae,
        "Object": model
    })

results_df = pd.DataFrame(results)
results_df = results_df.sort_values("R2", ascending=False)

print("\n===== RESULTS =====")
print(results_df[["Model", "R2", "RMSE", "MAE"]])


# =====================================================
# 6. SELECTION ET SAUVEGARDE DU MEILLEUR MODELE
# =====================================================

best_model_name = results_df.iloc[0]["Model"]
best_model = results_df.iloc[0]["Object"]

print("\nMeilleur modèle :", best_model_name)

joblib.dump(best_model, "best_model.pkl")
joblib.dump(X.columns.tolist(), "model_columns.pkl")
joblib.dump(imputer, "knn_imputer.pkl")

print("Modèle sauvegardé : best_model.pkl")
print("Colonnes sauvegardées : model_columns.pkl")
print("Imputer sauvegardé : knn_imputer.pkl")