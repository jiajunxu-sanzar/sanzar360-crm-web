from __future__ import annotations

import pandas as pd


def funnel_counts(df: pd.DataFrame) -> dict[str, int]:
    if df.empty or "estado" not in df.columns:
        return {}
    return df["estado"].fillna("").astype(str).replace("", "Sin estado").value_counts().to_dict()


def value_counts(df: pd.DataFrame, column: str, *, top: int = 10) -> dict[str, int]:
    if df.empty or column not in df.columns:
        return {}
    return (
        df[column]
        .fillna("")
        .astype(str)
        .replace("", "Sin dato")
        .value_counts()
        .head(top)
        .to_dict()
    )


def kpi_summary(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {"contactos": 0, "clientes": 0, "proximas_acciones": 0, "sin_estado": 0}
    estado = df.get("estado", pd.Series(dtype=str)).fillna("").astype(str)
    next_actions = df.get("proxima_accion_fecha", pd.Series(dtype=str)).fillna("").astype(str)
    return {
        "contactos": int(len(df)),
        "clientes": int((estado.str.lower() == "cliente").sum()),
        "proximas_acciones": int((next_actions.str.strip() != "").sum()),
        "sin_estado": int((estado.str.strip() == "").sum()),
    }
