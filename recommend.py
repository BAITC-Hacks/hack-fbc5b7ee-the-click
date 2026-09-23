"""
Сборка итоговой таблицы рекомендованных заказов поставщикам.

recommended_qty = max(0, round_up_to_moq(
    forecast_over_period + safety_stock - current_stock - in_transit_arriving_soon
))
"""

import math
import numpy as np
import pandas as pd

try:
    from . import config
except ImportError:
    import config


def _urgency(months_cover: float) -> str:
    if months_cover <= 0:
        return "Критично"
    if months_cover < 1:
        return "Высокая"
    if months_cover < 2:
        return "Средняя"
    return "Низкая"


def _round_up_to_multiple(qty: float, multiple: float) -> float:
    if multiple <= 0:
        multiple = 1
    return math.ceil(qty / multiple) * multiple


def build_recommendations(
    supplier_name: str,
    names: pd.Series,
    forecast_df: pd.DataFrame,
    current_stock: pd.DataFrame,
    transit: pd.DataFrame,
    moq: pd.DataFrame,
    outlier_flags: pd.DataFrame,
    stockout_flags: pd.DataFrame,
) -> pd.DataFrame:

    df = forecast_df.merge(current_stock, on="sku", how="left")
    df = df.merge(transit, on="sku", how="left")
    df = df.merge(moq, on="sku", how="left")

    df["current_stock"] = df["current_stock"].fillna(0)
    df["in_transit_qty"] = df["in_transit_qty"].fillna(0)
    df["moq"] = df["moq"].fillna(1)

    # была ли компенсация дефицита / исключены ли выбросы за последние 3 мес
    recent_stockout = (
        stockout_flags.sort_values("period")
        .groupby("sku")["is_stockout"].apply(lambda s: bool(s.tail(3).any()))
        .rename("had_recent_stockout")
    )
    recent_outlier = (
        outlier_flags.groupby("sku")["is_outlier"].sum().rename("outliers_excluded")
    )
    df = df.merge(recent_stockout, on="sku", how="left")
    df = df.merge(recent_outlier, on="sku", how="left")
    df["had_recent_stockout"] = df["had_recent_stockout"].fillna(False)
    df["outliers_excluded"] = df["outliers_excluded"].fillna(0).astype(int)

    safety_stock = config.SAFETY_STOCK_COEF * df["forecast_next_month"]
    need_over_period = df["forecast_next_month"] + safety_stock
    gap = need_over_period - df["current_stock"] - df["in_transit_qty"]
    gap = gap.clip(lower=0)

    df["recommended_qty"] = [
        _round_up_to_multiple(q, m) if q > 0 else 0
        for q, m in zip(gap, df["moq"])
    ]

    months_cover = np.where(
        df["forecast_next_month"] > 0,
        df["current_stock"] / df["forecast_next_month"],
        np.where(df["current_stock"] > 0, 99, 0),
    )
    df["months_of_cover"] = np.round(months_cover, 2)
    df["urgency"] = [_urgency(m) for m in months_cover]

    name_map = names.drop_duplicates("sku").set_index("sku")["name"]
    df["name"] = df["sku"].map(name_map).fillna(df["sku"])
    df["supplier"] = supplier_name

    explanations = []
    for _, row in df.iterrows():
        parts = [f"база спроса ≈{row['base_level']:.0f} шт/мес (история {row['months_of_history']} мес.)"]
        if row["has_seasonality"]:
            parts.append(f"сезонность ×{row['seasonal_index_next']:.2f}")
        if row["growth_coef"] != 1.0:
            trend = "рост" if row["growth_coef"] > 1 else "снижение"
            parts.append(f"{trend} спроса ×{row['growth_coef']:.2f}")
        if row["outliers_excluded"] > 0:
            parts.append(f"исключено разовых крупных заказов: {int(row['outliers_excluded'])}")
        if row["had_recent_stockout"]:
            parts.append("продажи скорректированы вверх из-за дефицита на складе")
        parts.append(f"прогноз след. месяц ≈{row['forecast_next_month']:.0f} шт")
        parts.append(f"остаток {row['current_stock']:.0f} + в пути {row['in_transit_qty']:.0f}")
        explanations.append("; ".join(parts))
    df["explanation"] = explanations

    cols = [
        "supplier", "sku", "name", "current_stock", "in_transit_qty",
        "forecast_next_month", "recommended_qty", "months_of_cover", "urgency",
        "explanation", "moq",
    ]
    return df[cols].sort_values(["urgency", "recommended_qty"], ascending=[True, False])
