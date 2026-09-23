"""
Оценка и компенсация упущенного спроса в периоды отсутствия товара (stockout).

У нас есть только помесячные остатки (не дневные), поэтому месяц считаем
"дефицитным" для SKU, если остаток на конец месяца близок к нулю
(<= STOCKOUT_STOCK_THRESHOLD от среднемесячных продаж SKU за всю историю).
Логика: если весь месяц заканчивается почти на нуле — вероятно, товара не
хватало и часть спроса не была реализована и не попала в продажи.

Компенсация: продажи дефицитного месяца заменяются медианой продаж
по НЕ дефицитным месяцам того же календарного месяца года (сезонного
аналога), а если такого аналога нет — медианой по всем не дефицитным
месяцам SKU. Если данных мало — компенсация не применяется (недостаточно
оснований), это тоже отражается в обосновании.
"""

import numpy as np
import pandas as pd

try:
    from . import config
except ImportError:
    import config


def compensate(monthly_sales: pd.DataFrame, monthly_stock: pd.DataFrame) -> pd.DataFrame:
    """
    monthly_sales: sku, period, qty_clean (после исключения выбросов)
    monthly_stock: sku, period, value (остаток на конец месяца)
    Возвращает monthly_sales + колонки: is_stockout, qty_adjusted
    """
    stock = monthly_stock.rename(columns={"value": "stock_end"})
    df = monthly_sales.merge(stock[["sku", "period", "stock_end"]], on=["sku", "period"], how="left")

    df["qty_adjusted"] = df["qty_clean"]
    df["is_stockout"] = False

    for sku, g in df.groupby("sku"):
        avg_monthly = g["qty_clean"].mean()
        if avg_monthly <= 0:
            continue
        threshold = config.STOCKOUT_STOCK_THRESHOLD * avg_monthly
        stockout_mask = g["stock_end"].fillna(0) <= threshold
        idx_stockout = g.index[stockout_mask]
        idx_normal = g.index[~stockout_mask]
        if len(idx_stockout) == 0 or len(idx_normal) < 3:
            continue

        df.loc[idx_stockout, "is_stockout"] = True

        for i in idx_stockout:
            month_num = df.at[i, "period"].month
            same_month_normal = [
                j for j in idx_normal if df.at[j, "period"].month == month_num
            ]
            if same_month_normal:
                replacement = np.median(df.loc[same_month_normal, "qty_clean"])
            else:
                replacement = np.median(df.loc[idx_normal, "qty_clean"])
            # компенсируем только вверх — если фактические продажи и так выше оценки, не занижаем
            df.at[i, "qty_adjusted"] = max(df.at[i, "qty_clean"], replacement)

    return df
