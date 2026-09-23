import pandas as pd

from forecast import build_forecast
from outliers import flag_outliers, monthly_from_transactions
from stockout import compensate


def test_one_time_order_is_removed_from_regular_demand():
    rows = [
        {"sku": "A", "period": pd.Period(f"2026-{month:02d}"), "qty": 10}
        for month in range(1, 7)
    ]
    rows.append({"sku": "A", "period": pd.Period("2026-03"), "qty": 500})
    transactions = pd.DataFrame(rows)
    flagged = flag_outliers(transactions)
    monthly = monthly_from_transactions(flagged)
    march = monthly.loc[monthly["period"].eq(pd.Period("2026-03"))].iloc[0]
    assert march["qty_raw"] == 510
    assert march["qty_clean"] == 10


def test_stockout_compensation_increases_adjusted_demand():
    sales = pd.DataFrame(
        {
            "sku": ["A"] * 4,
            "period": pd.period_range("2026-01", periods=4, freq="M"),
            "qty_clean": [100, 100, 5, 100],
        }
    )
    stock = pd.DataFrame(
        {
            "sku": ["A"] * 4,
            "period": pd.period_range("2026-01", periods=4, freq="M"),
            "value": [100, 100, 0, 100],
        }
    )
    adjusted = compensate(sales, stock)
    row = adjusted.loc[adjusted["period"].eq(pd.Period("2026-03"))].iloc[0]
    assert row["is_stockout"]
    assert row["qty_adjusted"] > row["qty_clean"]


def test_forecast_contains_growth_and_seasonality_fields():
    periods = pd.period_range("2025-01", periods=18, freq="M")
    monthly = pd.DataFrame(
        {
            "sku": ["A"] * len(periods),
            "period": periods,
            "qty_adjusted": [100 + (i % 6) * 10 for i in range(len(periods))],
        }
    )
    result = build_forecast(monthly, periods[-1])
    assert result.iloc[0]["has_seasonality"]
    assert "growth_coef" in result
    assert result.iloc[0]["forecast_next_month"] > 0
