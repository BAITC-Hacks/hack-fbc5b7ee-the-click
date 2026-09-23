"""
Выявление разовых крупных заказов (в т.ч. крупных продаж одному клиенту)
в построчной динамике продаж, чтобы не давать им искажать расчёт
регулярной потребности.

Обезличенного ID клиента в исходных данных нет, но каждая строка привязана
к номеру документа (одна отгрузка = один клиент/заказ на дату), поэтому
номер документа — рабочая замена ID клиента для целей этой проверки.

Метод: для каждого SKU считаем типичный размер строки продажи (медиану
и MAD/лог-std по истории). Строку считаем выбросом, если одновременно:
  1) она в OUTLIER_MULT_OF_MEDIAN раз больше медианы по SKU, и
  2) её z-score по логарифму объёма выше OUTLIER_ZSCORE, и
  3) объём не меньше OUTLIER_MIN_QTY (чтобы не ловить шум на мелких SKU).
"""

import numpy as np
import pandas as pd

from . import config


def flag_outliers(transactions: pd.DataFrame) -> pd.DataFrame:
    """Возвращает transactions с доп. колонкой is_outlier (bool)."""
    df = transactions.copy()
    df["is_outlier"] = False

    for sku, g in df.groupby("sku"):
        if len(g) < 5:
            continue  # мало данных, чтобы отличить выброс от нормы
        log_qty = np.log1p(g["qty"])
        med = np.median(g["qty"])
        std = log_qty.std(ddof=0)
        if std == 0 or med == 0:
            continue
        z = (log_qty - log_qty.mean()) / std
        mask = (
            (g["qty"] >= config.OUTLIER_MIN_QTY)
            & (g["qty"] >= config.OUTLIER_MULT_OF_MEDIAN * med)
            & (z >= config.OUTLIER_ZSCORE)
        )
        df.loc[g.index[mask], "is_outlier"] = True

    return df


def monthly_from_transactions(transactions_flagged: pd.DataFrame) -> pd.DataFrame:
    """
    Агрегирует построчные продажи в помесячные суммы двух видов:
      qty_raw    — как есть (все строки)
      qty_clean  — без выбросов (регулярный спрос)
    """
    g = transactions_flagged.groupby(["sku", "period"])
    out = g["qty"].sum().rename("qty_raw").reset_index()
    clean = (
        transactions_flagged[~transactions_flagged["is_outlier"]]
        .groupby(["sku", "period"])["qty"].sum()
        .rename("qty_clean")
        .reset_index()
    )
    out = out.merge(clean, on=["sku", "period"], how="left")
    out["qty_clean"] = out["qty_clean"].fillna(0)
    return out
