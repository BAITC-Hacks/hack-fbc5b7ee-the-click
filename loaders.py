"""
Загрузка «сырых» выгрузок 1С в нормализованный вид.
Файлы у поставщиков имеют разные названия колонок, но одинаковую суть —
здесь мы приводим всё к единой схеме, дальше пайплайн уже не думает,
от какого поставщика пришли данные.
"""

import re
import numpy as np
import pandas as pd
import os

MONTH_RE = re.compile(
    r"(янв|февр|март|апр|май|июнь|июль|авг|сент|окт|нояб|дек)\S*\.?\s*(\d{4})",
    re.IGNORECASE,
)

RU_MONTH_NUM = {
    "янв": 1, "февр": 2, "март": 3, "апр": 4, "май": 5, "июнь": 6,
    "июль": 7, "авг": 8, "сент": 9, "окт": 10, "нояб": 11, "дек": 12,
}


def _month_col_to_period(col_name: str):
    """'янв. 2024' / 'Январь 2024 г.' -> pandas.Period('2024-01') либо None."""
    m = MONTH_RE.search(str(col_name))
    if not m:
        return None
    root, year = m.group(1).lower(), int(m.group(2))
    month = RU_MONTH_NUM.get(root)
    if month is None:
        return None
    return pd.Period(freq="M", year=year, month=month)


def _find_header_row(path, sheet, max_scan=4):
    """Ищем строку, где встречается 'Номенклатура.Код' / 'Код 1с' — это заголовок."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None, nrows=max_scan)
    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).tolist()
        if any(v in ("Номенклатура.Код", "Код 1с") for v in row):
            return i
    return 0


def load_monthly_wide(path, key_col_candidates=("Номенклатура.Код", "Код 1с")):
    """
    Загружает 'широкий' файл (ежемесячные продажи ИЛИ остатки) и переводит
    его в длинный формат: sku_code, name, period (Period[M]), value.
    """
    header_row = _find_header_row(path, 0)
    df = pd.read_excel(path, sheet_name=0, header=header_row)
    # вторая строка под заголовком иногда служебная ('Количество' / NaN) — выкидываем её
    if len(df) and df.iloc[0].isna().sum() >= len(df.columns) - 2:
        df = df.iloc[1:].reset_index(drop=True)

    key_col = next((c for c in key_col_candidates if c in df.columns), None)
    if key_col is None:
        raise ValueError(f"Не найдена колонка с кодом артикула в {path}: {df.columns.tolist()}")

    name_col = "Номенклатура" if "Номенклатура" in df.columns else None

    month_cols = {c: _month_col_to_period(c) for c in df.columns}
    month_cols = {c: p for c, p in month_cols.items() if p is not None}

    df = df[df[key_col].notna()].copy()
    df[key_col] = df[key_col].astype(str).str.strip()

    long_rows = []
    for _, row in df.iterrows():
        sku = row[key_col]
        name = row[name_col] if name_col else sku
        for col, period in month_cols.items():
            val = row[col]
            if pd.isna(val):
                continue
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
            long_rows.append((sku, name, period, val))

    out = pd.DataFrame(long_rows, columns=["sku", "name", "period", "value"])
    # если у одного sku несколько строк-дублей — суммируем
    out = out.groupby(["sku", "name", "period"], as_index=False)["value"].sum()
    return out


def load_transactions(path):
    """
    'Динамика продаж' — построчные отгрузки. Одна строка = одна позиция
    в одном документе. Количество приходит со знаком минус (списание со склада).
    """
    df = pd.read_excel(path, sheet_name=0)
    df = df[df["Код"].notna()].copy()
    df["Код"] = df["Код"].astype(str).str.strip()
    df["Дата"] = pd.to_datetime(df["Дата"], dayfirst=True, errors="coerce")
    df["Количество"] = pd.to_numeric(df["Количество"], errors="coerce")
    df = df.dropna(subset=["Дата", "Количество"])
    df["qty"] = df["Количество"].abs()
    df["period"] = df["Дата"].dt.to_period("M")
    df = df.rename(columns={"Код": "sku", "Номенклатура": "name", "Номер": "doc_no"})
    return df[["sku", "name", "doc_no", "Дата", "period", "qty"]]


def load_moq(path, key_col, val_col):
    df = pd.read_excel(path, sheet_name=0)
    df = df[df[key_col].notna()].copy()
    df[key_col] = df[key_col].astype(str).str.strip()
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce").fillna(1)
    df.loc[df[val_col] <= 0, val_col] = 1
    out = df[[key_col, val_col]].drop_duplicates(subset=[key_col])
    return out.rename(columns={key_col: "sku", val_col: "moq"})


def load_transit_generic(path, sheet, key_col):
    """
    У SE и IEK транзитные файлы устроены по-разному:
      - SE: один "мастер"-лист, транзит лежит в столбце, где в названии
        встречается "в пути".
      - IEK: каждая колонка справа — отдельная поставка (заказ поставщику),
        в заголовке есть дата ожидаемого поступления; суммируем все колонки.
    Возвращаем: sku, in_transit_qty, nearest_eta (дата или None).
    """
    header_row = _find_header_row(path, sheet)
    df = pd.read_excel(path, sheet_name=sheet, header=header_row)
    if key_col not in df.columns:
        raise ValueError(f"Не найдена {key_col} в {path}")
    df = df[df[key_col].notna()].copy()
    df[key_col] = df[key_col].astype(str).str.strip()

    transit_cols = [c for c in df.columns if "в пути" in str(c).lower()]
    date_cols = [c for c in df.columns if re.search(r"\d{4}", str(c)) and "в пути" not in str(c).lower()
                 and c != key_col]

    result = pd.DataFrame({"sku": df[key_col]})

    if transit_cols:
        result["in_transit_qty"] = pd.to_numeric(df[transit_cols[0]], errors="coerce").fillna(0)
    elif date_cols:
        qty = df[date_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
        result["in_transit_qty"] = qty.sum(axis=1)
    else:
        result["in_transit_qty"] = 0.0

    def nearest_eta(row):
        best = None
        for c in date_cols:
            v = df.at[row.name, c]
            if pd.isna(v) or v == 0:
                continue
            m = re.search(r"(\d{1,2})[.\s](\d{1,2})[.\s](\d{4})", str(c))
            if m:
                try:
                    d = pd.Timestamp(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                    if best is None or d < best:
                        best = d
                except ValueError:
                    continue
        return best

    if date_cols:
        result["eta"] = df.apply(nearest_eta, axis=1)
    else:
        result["eta"] = pd.NaT

    result = result.groupby("sku", as_index=False).agg(
        in_transit_qty=("in_transit_qty", "sum"),
        eta=("eta", "min"),
    )
    return result
