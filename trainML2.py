import pandas as pd
import numpy as np
import joblib

from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from sklearn.model_selection import GridSearchCV

from xgboost import XGBRegressor


# =========================
# CONFIG
# =========================

FILE = "DATASET_FINAL_CIL_V5.xlsx"
TARGET = "TARGET_REJET_JPLUS1"

TEST_RATIO = 0.20

DROP_COLS = [
    "SHIFT_DATE",
    "SHIFT_TIME",
    "SHIFT_DATETIME"
]


# =========================
# FUNCTIONS
# =========================

def evaluate(y_true, y_pred):
    r2 = r2_score(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    return r2, rmse, mae


def add_lag_rolling_features(df, target):
    df = df.copy()

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    numeric_cols = [c for c in numeric_cols if c != target]

    important_keywords = [
        "SOLIDE_AU",
        "LIQUIDE_AU",
        "CHARBON_AU",
        "PH",
        "TOX",
        "TCCY",
        "Grade",
        "share",
        "Tonnage"
    ]

    selected_cols = [
        c for c in numeric_cols
        if any(k.upper() in c.upper() for k in important_keywords)
    ]

    new_features = {}

    for col in selected_cols:
        new_features[f"{col}_lag1"] = df[col].shift(1)
        new_features[f"{col}_lag2"] = df[col].shift(2)
        new_features[f"{col}_roll3_mean"] = df[col].rolling(window=3, min_periods=1).mean()
        new_features[f"{col}_roll3_std"] = df[col].rolling(window=3, min_periods=1).std()

    df_new = pd.DataFrame(new_features, index=df.index)

    df_out = pd.concat([df, df_new], axis=1)
    df_out = df_out.copy()

    return df_out


def remove_constant_columns(X):
    std = X.std(numeric_only=True)
    keep_cols = std[std > 0].index.tolist()
    return X[keep_cols]


def select_by_target_corr(X, y, threshold=0.08):
    corr_with_target = X.corrwith(y).abs()
    selected = corr_with_target[corr_with_target > threshold].index.tolist()

    if len(selected) == 0:
        print("⚠️ Aucune feature sélectionnée avec ce seuil. Retour à toutes les features.")
        return X

    return X[selected]


def remove_highly_correlated_features(X, threshold=0.95):
    corr_matrix = X.corr().abs()

    upper = corr_matrix.where(
        np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
    )

    to_drop = [
        col for col in upper.columns
        if any(upper[col] > threshold)
    ]

    print(f"Variables supprimées car corrélées > {threshold}: {len(to_drop)}")

    X_reduced = X.drop(columns=to_drop, errors="ignore")

    return X_reduced, to_drop


# =========================
# LOAD DATA
# =========================

df = pd.read_excel(FILE)

if "SHIFT_DATE" in df.columns:
    df["SHIFT_DATE"] = pd.to_datetime(df["SHIFT_DATE"], errors="coerce")

if "SHIFT_DATETIME" in df.columns:
    df["SHIFT_DATETIME"] = pd.to_datetime(
        df["SHIFT_DATETIME"],
        errors="coerce",
        utc=True
    ).dt.tz_localize(None)

sort_cols = [c for c in ["SHIFT_DATE", "SHIFT_DATETIME", "SHIFT"] if c in df.columns]
if sort_cols:
    df = df.sort_values(sort_cols).reset_index(drop=True)


# =========================
# FEATURE ENGINEERING
# =========================

df = add_lag_rolling_features(df, TARGET)


# =========================
# PREPARE DATA
# =========================

if TARGET not in df.columns:
    raise ValueError(f"Target absente du fichier: {TARGET}")

df_model = df.dropna(subset=[TARGET]).copy()

drop_cols_present = [c for c in DROP_COLS if c in df_model.columns]

X = df_model.drop(columns=[TARGET] + drop_cols_present, errors="ignore")
y = df_model[TARGET].copy()

X = X.apply(pd.to_numeric, errors="coerce")
X = X.dropna(axis=1, how="all")
X = X.fillna(X.median(numeric_only=True))
X = X.fillna(0)

print("\n===== DATA INFO =====")
print("Nombre lignes:", len(X))
print("Nombre features initial:", X.shape[1])


# =========================
# FEATURE SELECTION
# =========================

X = remove_constant_columns(X)
print("Après suppression constantes:", X.shape[1])

X = select_by_target_corr(X, y, threshold=0.08)
print("Après sélection corr target > 0.08:", X.shape[1])

X, dropped_corr_features = remove_highly_correlated_features(X, threshold=0.95)
print("Après suppression corrélées > 0.95:", X.shape[1])


# =========================
# SPLIT CHRONOLOGIQUE
# =========================

n = len(X)
split_idx = int(n * (1 - TEST_RATIO))

X_train = X.iloc[:split_idx]
X_test = X.iloc[split_idx:]

y_train = y.iloc[:split_idx]
y_test = y.iloc[split_idx:]

print("\nTrain:", len(X_train))
print("Test :", len(X_test))


# =========================
# MODELS
# =========================

models = {}

models["Ridge"] = Ridge(alpha=1.0)

models["RandomForest"] = RandomForestRegressor(
    n_estimators=600,
    max_depth=10,
    min_samples_leaf=2,
    random_state=42,
    n_jobs=-1
)

# GradientBoosting optimisé
gb_params = {
    "n_estimators": [200, 400, 600],
    "learning_rate": [0.03, 0.05, 0.08],
    "max_depth": [2, 3, 4],
    "min_samples_leaf": [1, 2, 4]
}

gb_grid = GridSearchCV(
    GradientBoostingRegressor(random_state=42),
    gb_params,
    scoring="r2",
    cv=3,
    n_jobs=-1
)

gb_grid.fit(X_train, y_train)

print("\nBest GradientBoosting params:")
print(gb_grid.best_params_)

models["GradientBoosting_Optimized"] = gb_grid.best_estimator_


# XGBoost optimisé simple
xgb_params = {
    "n_estimators": [200, 400, 600],
    "learning_rate": [0.03, 0.05, 0.08],
    "max_depth": [2, 3, 4],
    "subsample": [0.8, 1.0],
    "colsample_bytree": [0.8, 1.0]
}

xgb_grid = GridSearchCV(
    XGBRegressor(
        objective="reg:squarederror",
        random_state=42,
        n_jobs=-1
    ),
    xgb_params,
    scoring="r2",
    cv=3,
    n_jobs=-1
)

xgb_grid.fit(X_train, y_train)

print("\nBest XGBoost params:")
print(xgb_grid.best_params_)

models["XGBoost_Optimized"] = xgb_grid.best_estimator_


# =========================
# TRAIN + EVALUATE
# =========================

results = []

for name, model in models.items():
    if name not in ["GradientBoosting_Optimized", "XGBoost_Optimized"]:
        model.fit(X_train, y_train)

    pred = model.predict(X_test)

    r2, rmse, mae = evaluate(y_test, pred)

    results.append((name, r2, rmse, mae, model, pred))

results_df = pd.DataFrame(
    results,
    columns=["Model", "R2", "RMSE", "MAE", "Object", "Pred"]
).sort_values("R2", ascending=False).reset_index(drop=True)

print("\n===== RESULTS OPTIMISÉS =====")
print(results_df[["Model", "R2", "RMSE", "MAE"]])


# =========================
# BEST MODEL
# =========================

best_name = results_df.loc[0, "Model"]
best_model = results_df.loc[0, "Object"]
best_pred = results_df.loc[0, "Pred"]

print("\n✅ Best model:", best_name)


# =========================
# SAVE MODEL
# =========================

joblib.dump(best_model, "best_model.pkl")
joblib.dump(X.columns.tolist(), "model_columns.pkl")

print("✅ Modèle sauvegardé: best_model.pkl")
print("✅ Colonnes sauvegardées: model_columns.pkl")


# =========================
# SAVE OUTPUTS
# =========================

results_df[["Model", "R2", "RMSE", "MAE"]].to_excel(
    "COMPARAISON_MODELES_OPTIMISES_XGBOOST.xlsx",
    index=False
)

pred_out = df_model.iloc[split_idx:].copy()
pred_out["REJET_REEL"] = y_test.values
pred_out["REJET_PREDIT"] = best_pred
pred_out["ERREUR"] = pred_out["REJET_REEL"] - pred_out["REJET_PREDIT"]
pred_out["ABS_ERREUR"] = np.abs(pred_out["ERREUR"])

pred_out.to_excel("PREDICTIONS_MODELE_OPTIMISE_XGBOOST.xlsx", index=False)

pd.DataFrame({
    "dropped_corr_features": dropped_corr_features
}).to_excel("FEATURES_SUPPRIMEES_CORR_095.xlsx", index=False)

print("✅ Résultats sauvegardés")