"""
Прогноз спроса на следующий период: тренд (устойчивый рост/спад спроса)
+ сезонность, поверх очищенных от выбросов и дефицита продаж.

Метод классический (ratio-to-moving-average), выбран сознательно вместо
"чёрного ящика" — весь расчёт объясним по каждому шагу, что требуется по
условиям задачи:

  1. seasonal_index[month] = медиана(qty_adjusted за этот календарный месяц)
                              / медиана(qty_adjusted за все месяцы)
     Если история короче 12 мес. — индекс = 1.0 для всех месяцев
     (недостаточно данных, чтобы отделить сезонность от шума).

  2. deseasonalized[t] = qty_adjusted[t] / seasonal_index[month(t)]
     growth = среднее отношение deseasonalized последних 3 месяцев
              к deseasonalized предыдущих 3 месяцев (клип в [0.5, 2.0],
              чтобы единичный скачок не улетал в прогноз без ограничений).

  3. base_level = медиана deseasonalized за последние 6 месяцев
     forecast[next_month] = base_level * growth * seasonal_index[next_month]
"""

import numpy as np
import pandas as pd


def build_forecast(monthly: pd.DataFrame, as_of: pd.Period) -> pd.DataFrame:
    """
    monthly: sku, period, qty_adjusted
    Возвращает по одному прогнозу на sku: forecast_next_month, seasonal_index_next,
    growth_coef, base_level, months_of_history, has_seasonality
    """
    rows = []
    next_period = as_of + 1

    for sku, g in monthly.groupby("sku"):
        g = g.sort_values("period")
        g = g[g["period"] <= as_of]
        if g.empty:
            continue

        n_months = g["period"].nunique()
        has_seasonality = n_months >= 12

        if has_seasonality:
            month_med = g.groupby(g["period"].dt.month)["qty_adjusted"].median()
            overall_med = g["qty_adjusted"].median()
            if overall_med > 0:
                seasonal_index = (month_med / overall_med).to_dict()
            else:
                seasonal_index = {}
            si_next = seasonal_index.get(next_period.month, 1.0)
            deseason = g.set_index("period")["qty_adjusted"] / g["period"].dt.month.map(
                lambda m: seasonal_index.get(m, 1.0)
            ).values
        else:
            si_next = 1.0
            deseason = g.set_index("period")["qty_adjusted"]

        deseason = deseason.sort_index()
        if len(deseason) >= 6:
            recent = deseason.iloc[-3:].mean()
            prior = deseason.iloc[-6:-3].mean()
            growth = recent / prior if prior > 0 else 1.0
        else:
            growth = 1.0
        growth = float(np.clip(growth, 0.5, 2.0))

        base_level = deseason.iloc[-6:].median() if len(deseason) else 0.0
        forecast_next = max(0.0, base_level * growth * si_next)

        rows.append({
            "sku": sku,
            "months_of_history": n_months,
            "has_seasonality": has_seasonality,
            "seasonal_index_next": round(float(si_next), 2),
            "growth_coef": round(growth, 2),
            "base_level": round(float(base_level), 1),
            "forecast_next_month": round(float(forecast_next), 1),
        })

    return pd.DataFrame(rows)
