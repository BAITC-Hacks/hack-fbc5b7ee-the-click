"""
Конфигурация источников данных по поставщикам.
Чтобы подключить нового поставщика — добавь новый блок сюда,
остальной код (loaders/pipeline) ничего не знает про конкретных поставщиков.
"""

import os

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = PROJECT_DIR

SUPPLIERS = {
    "Systeme Electric": {
        "dir": DATA_DIR,
        "monthly_sales": "Ежемесячные продажи в кол-м выражении SystemElectric 2024-2026.xlsx",
        "monthly_stock": "Ежемесячные остатки SystemElectric 2024-2026.xlsx",
        "transactions": "Динамика продаж_Syseme Electric_2025-2026.xlsx",
        "moq": "MOQ SystemElectric.xlsx",
        "moq_key_col": "Номенклатура.Код",
        "moq_val_col": "Кратность",
        "transit": "Товар в пути_SystemElectric на 22.09.2026.xlsx",
        "transit_sheet": "TDSheet",
        "transit_key_col": "Код 1с",
        # для этого файла колонки с "в пути" ищем по подстроке
    },
    "IEK": {
        "dir": DATA_DIR,
        "monthly_sales": "Ежемесячные продажи в количественном выражении за последние 2 года.xlsx",
        "monthly_stock": "Ежемесячные остатки продукции за последние 2 года  ИЭК.xlsx",
        "transactions": "Динамика продаж_2025-2026.xlsx",
        "moq": "MOQ  ИЭК.xlsx",
        "moq_key_col": "Код 1с",
        "moq_val_col": "Мин. разр. к отгр.",
        "transit": "Путь ИЭК 22.09.2026.xlsx",
        "transit_sheet": "Лист4",
        "transit_key_col": "Код 1с",
    },
}

# --- допущения расчёта (вынесены сюда, чтобы их было легко покрутить) ---
DEFAULT_LEAD_TIME_DAYS = 30       # если для поставщика нет своих данных о сроке поставки
DEFAULT_REVIEW_PERIOD_DAYS = 30   # как часто реально делают заказ
SAFETY_STOCK_COEF = 0.5           # доля среднемесячного спроса, идущая в страховой запас
STOCKOUT_STOCK_THRESHOLD = 0.02   # остаток <= 2% от среднемесячных продаж считается "дефицитом"
OUTLIER_MIN_QTY = 5               # не считаем выбросом слишком маленькие партии
OUTLIER_ZSCORE = 3.0              # порог z-score по логарифму размера строки продажи
OUTLIER_MULT_OF_MEDIAN = 5.0      # и одновременно >= 5x медианного размера строки продажи по SKU
