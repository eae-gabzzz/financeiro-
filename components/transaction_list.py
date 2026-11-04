"""Listagem de movimentações com editar/excluir."""
from html import escape

import streamlit as st

from services.transactions import INCOME, TYPE_LABELS
from utils.formatting import format_brl, format_date_br
from utils.icons import ICONS

PAGE_SIZE = 25


def render_empty_state() -> None:
    st.markdown(
        f'<div class="ff-empty"><span class="ff-empty-icon">{ICONS["inbox"]}</span>'
        '<h3>Seu histórico financeiro começa aqui.</h3>'
        '<p>Adicione sua primeira receita ou despesa para acompanhar seu dinheiro.</p>'
        '<p class="ff-hint">Toque no botão + abaixo.</p></div>', unsafe_allow_html=True)


def _row_html(tx: dict) -> str:
    income = tx["type"] == INCOME
    css = "income" if income else "expense"
    amount = ("+" + format_brl(tx["amount_cents"])) if income else format_brl(-tx["amount_cents"])
    meta = f'{escape(tx["category"])} · {format_date_br(tx["date"])} · {TYPE_LABELS[tx["type"]]}'
    notes = f' title="{escape(tx["notes"])}"' if tx.get("notes") else ""
    return (f'<div class="ff-row ff-{css}"{notes}><span class="ff-icon">{ICONS[css]}</span>'
            f'<div class="ff-row-main"><div class="ff-desc">{escape(tx["description"])}</div>'
            f'<div class="ff-meta">{meta}</div></div>'
            f'<div class="ff-amount {"ff-pos" if income else "ff-neg"}">{amount}</div></div>')


def render_transaction_list(items, *, on_edit, on_delete_request, on_delete_confirm,
                            on_delete_cancel, pending_delete=None, on_more=None) -> None:
    shown = st.session_state.get("shown", PAGE_SIZE)
    for tx in items[:shown]:
        if pending_delete == tx["id"]:
            st.warning(f'Excluir "{tx["description"]}" ({format_brl(tx["amount_cents"])})? Esta ação não pode ser desfeita.')
            c1, c2 = st.columns(2)
            c1.button("Confirmar exclusão", key=f"yes_{tx['id']}", type="primary",
                      use_container_width=True, on_click=on_delete_confirm)
            c2.button("Manter", key=f"no_{tx['id']}", use_container_width=True, on_click=on_delete_cancel)
            continue
        with st.container(key=f"row_{tx['id']}"):
            main, edit, delete = st.columns([7, 1.3, 1.3], vertical_alignment="center")
            main.markdown(_row_html(tx), unsafe_allow_html=True)
            edit.button("Editar", key=f"edit_{tx['id']}", icon=":material/edit:",
                        use_container_width=True, on_click=on_edit, args=(tx,))
            delete.button("Excluir", key=f"del_{tx['id']}", icon=":material/delete:",
                          use_container_width=True, on_click=on_delete_request, args=(tx["id"],))
    if len(items) > shown and on_more:
        st.button(f"Mostrar mais ({len(items) - shown} restantes)", key="more", on_click=on_more)
