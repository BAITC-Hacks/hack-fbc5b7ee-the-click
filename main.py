"""Run the complete replenishment pipeline from Excel files to dashboard outputs."""

from pathlib import Path

import pandas as pd

import config
from build_dashboard import main as build_dashboard
from forecast import build_forecast
from loaders import load_monthly_wide, load_moq, load_transactions, load_transit_generic
from outliers import flag_outliers, monthly_from_transactions
from recommend import build_recommendations
from stockout import compensate


ROOT = Path(__file__).resolve().parent


def _path(supplier: dict, key: str) -> Path:
    return Path(supplier["dir"]) / supplier[key]


def _latest_stock(stock: pd.DataFrame) -> pd.DataFrame:
    latest_period = stock.groupby("sku")["period"].transform("max")
    return (
        stock.loc[stock["period"].eq(latest_period), ["sku", "value"]]
        .groupby("sku", as_index=False)["value"]
        .sum()
        .rename(columns={"value": "current_stock"})
    )


def _prepare_monthly(
    monthly_sales: pd.DataFrame,
    transaction_monthly: pd.DataFrame,
    stock: pd.DataFrame,
) -> pd.DataFrame:
    monthly = monthly_sales.rename(columns={"value": "qty_clean"})[
        ["sku", "name", "period", "qty_clean"]
    ].copy()
    transaction_monthly = transaction_monthly.rename(
        columns={"qty_raw": "transaction_qty_raw", "qty_clean": "transaction_qty_clean"}
    )
    monthly = monthly.merge(
        transaction_monthly[
            ["sku", "period", "transaction_qty_raw", "transaction_qty_clean"]
        ],
        on=["sku", "period"],
        how="left",
    )
    monthly["outlier_qty"] = (
        monthly["transaction_qty_raw"].fillna(0)
        - monthly["transaction_qty_clean"].fillna(0)
    ).clip(lower=0)
    monthly["qty_clean"] = (monthly["qty_clean"] - monthly["outlier_qty"]).clip(lower=0)
    monthly = monthly[["sku", "name", "period", "qty_clean"]]
    return compensate(monthly, stock)


def run_pipeline() -> pd.DataFrame:
    """Load every configured supplier and write the reproducible result files."""
    results = []
    for supplier_name, supplier in config.SUPPLIERS.items():
        monthly_sales = load_monthly_wide(_path(supplier, "monthly_sales"))
        stock = load_monthly_wide(_path(supplier, "monthly_stock"))
        transactions = flag_outliers(load_transactions(_path(supplier, "transactions")))
        transaction_monthly = monthly_from_transactions(transactions)
        monthly = _prepare_monthly(monthly_sales, transaction_monthly, stock)
        as_of = monthly["period"].max()
        forecast = build_forecast(monthly[["sku", "period", "qty_adjusted"]], as_of)
        transit = load_transit_generic(
            _path(supplier, "transit"),
            supplier["transit_sheet"],
            supplier["transit_key_col"],
        )
        moq = load_moq(
            _path(supplier, "moq"),
            supplier["moq_key_col"],
            supplier["moq_val_col"],
        )
        names = monthly_sales[["sku", "name"]].drop_duplicates()
        recommendations = build_recommendations(
            supplier_name,
            names,
            forecast,
            _latest_stock(stock),
            transit,
            moq,
            transactions.groupby("sku", as_index=False)["is_outlier"]
            .sum()
            .assign(period=as_of),
            monthly[["sku", "period", "is_stockout"]],
        )
        results.append(recommendations)

    output = pd.concat(results, ignore_index=True)
    output.to_csv(ROOT / "recommended_orders.csv", index=False, encoding="utf-8-sig")
    output.to_json(
        ROOT / "recommended_orders.json",
        orient="records",
        force_ascii=False,
    )
    build_dashboard()
    return output


if __name__ == "__main__":
    result = run_pipeline()
    print(f"Готово: {len(result)} рекомендаций записано в CSV, JSON и index.html")
