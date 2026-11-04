"""Três indicadores: Receita, Despesas e Saldo."""
import streamlit as st

from utils.formatting import format_brl
from utils.icons import ICONS


def _card(css: str, icon: str, label: str, cents: int) -> str:
    return (f'<div class="ff-card ff-{css}"><div class="ff-card-head"><span class="ff-icon">{ICONS[icon]}</span>'
            f'<span>{label}</span></div><div class="ff-value">{format_brl(cents)}</div></div>')


def render_summary(totals) -> None:
    balance_css = "balance" if totals.balance_cents >= 0 else "balance-neg"
    html = ('<div class="ff-cards">'
            + _card("income", "income", "Receita", totals.income_cents)
            + _card("expense", "expense", "Despesas", totals.expense_cents)
            + _card(balance_css, "wallet", "Saldo", totals.balance_cents)
            + "</div>")
    st.markdown(html, unsafe_allow_html=True)
