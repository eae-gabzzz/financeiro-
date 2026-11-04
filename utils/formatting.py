"""Formatação e conversão de valores monetários (sempre em centavos inteiros)."""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def format_brl(cents: int) -> str:
    """1234567 -> 'R$ 12.345,67'; negativos -> '-R$ 350,00'."""
    cents = int(cents)
    sign = "-" if cents < 0 else ""
    reais, centavos = divmod(abs(cents), 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def reais_to_cents(value) -> int:
    """Converte reais (float/str/Decimal) em centavos sem erro de ponto flutuante."""
    try:
        amount = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Valor inválido.") from exc
    if not amount.is_finite():
        raise ValueError("Valor inválido.")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_date_br(iso_date: str) -> str:
    """'2026-10-15' -> '15/10/2026'."""
    return date.fromisoformat(iso_date).strftime("%d/%m/%Y")
