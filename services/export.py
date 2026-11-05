"""Exportação CSV (compatível com Excel BR e protegida contra CSV injection)."""
from __future__ import annotations

import pandas as pd

from services.transactions import INCOME, TYPE_LABELS
from utils.formatting import format_date_br


def _safe(text: str) -> str:
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def to_csv(items) -> bytes:
    rows = []
    for tx in items:
        cents = tx["amount_cents"] if tx["type"] == INCOME else -tx["amount_cents"]
        rows.append({
            "Data": format_date_br(tx["date"]),
            "Tipo": TYPE_LABELS[tx["type"]],
            "Categoria": _safe(tx["category"]),
            "Descrição": _safe(tx["description"]),
            "Valor (R$)": f"{cents / 100:.2f}".replace(".", ","),
            "Observações": _safe(tx.get("notes", "")),
        })
    cols = ["Data", "Tipo", "Categoria", "Descrição", "Valor (R$)", "Observações"]
    return pd.DataFrame(rows, columns=cols).to_csv(index=False, sep=";").encode("utf-8-sig")


def monthly_summary_csv(items, year: int, month: int) -> bytes:
    """Gera resumo do mês com totais, quantidade de lançamentos e despesas por categoria."""
    from datetime import date

    date(year, month, 1)
    monthly_items = [item for item in items if item["date"][:7] == f"{year:04d}-{month:02d}"]
    income = sum(item["amount_cents"] for item in monthly_items if item["type"] == INCOME)
    expenses = sum(item["amount_cents"] for item in monthly_items if item["type"] != INCOME)
    rows = [
        {"Seção": "Resumo", "Indicador": "Receitas", "Valor (R$)": f"{income / 100:.2f}".replace(".", ",")},
        {"Seção": "Resumo", "Indicador": "Despesas", "Valor (R$)": f"{expenses / 100:.2f}".replace(".", ",")},
        {"Seção": "Resumo", "Indicador": "Saldo", "Valor (R$)": f"{(income - expenses) / 100:.2f}".replace(".", ",")},
        {"Seção": "Resumo", "Indicador": "Lançamentos", "Valor (R$)": str(len(monthly_items))},
    ]
    by_category = {}
    for item in monthly_items:
        if item["type"] == INCOME:
            continue
        by_category[item["category"]] = by_category.get(item["category"], 0) + item["amount_cents"]
    rows.extend(
        {"Seção": "Despesas por categoria", "Indicador": _safe(category),
         "Valor (R$)": f"{amount / 100:.2f}".replace(".", ",")}
        for category, amount in sorted(by_category.items(), key=lambda entry: entry[1], reverse=True)
    )
    return pd.DataFrame(rows, columns=["Seção", "Indicador", "Valor (R$)"]).to_csv(
        index=False, sep=";"
    ).encode("utf-8-sig")
