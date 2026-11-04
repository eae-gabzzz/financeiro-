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
