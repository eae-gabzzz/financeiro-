"""Tela principal: indicadores, movimentações (+ gráfico) e botão +."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from components.floating_button import render_fab
from components.summary_cards import render_summary
from components.transaction_list import PAGE_SIZE, render_empty_state, render_transaction_list
from services.auth import logout
from services.export import to_csv
from services.transactions import (EXPENSE, INCOME, TYPE_LABELS, TransactionError, delete_transaction,
                                   filter_transactions, list_transactions, summarize)
from views.transaction_form import open_form

TYPE_FILTER = {"Todas": None, "Receitas": INCOME, "Despesas": EXPENSE}


def _request_delete(tx_id):
    st.session_state["confirm_delete"] = tx_id


def _cancel_delete():
    st.session_state.pop("confirm_delete", None)


def _confirm_delete(uid):
    tx_id = st.session_state.pop("confirm_delete", None)
    try:
        delete_transaction(uid, tx_id)
        st.session_state["flash"] = "Movimentação excluída."
    except TransactionError as exc:
        st.session_state["flash_error"] = str(exc)


def _more():
    st.session_state["shown"] = st.session_state.get("shown", PAGE_SIZE) + PAGE_SIZE


def _render_chart(items) -> None:
    if not items:
        st.info("O gráfico aparece assim que houver movimentações.")
        return
    df = pd.DataFrame(items)
    df["Mês"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
    df["Valor"] = df["amount_cents"] / 100
    df["Tipo"] = df["type"].map(TYPE_LABELS)
    grouped = df.groupby(["Mês", "Tipo"], as_index=False)["Valor"].sum()
    fig = px.bar(grouped, x="Mês", y="Valor", color="Tipo", barmode="group",
                 color_discrete_map={"Receita": "#22C55E", "Despesa": "#F87171"})
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=0, r=0, t=10, b=0), yaxis_tickprefix="R$ ", legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)


def _filters(items) -> list[dict]:
    categories = sorted({t["category"] for t in items})
    options = ["Todas"] + categories
    if st.session_state.get("f_cat") not in options:
        st.session_state["f_cat"] = "Todas"
    c1, c2 = st.columns([2, 1])
    search = c1.text_input("Buscar", key="f_search", placeholder="Buscar por descrição…", label_visibility="collapsed")
    kind = c2.selectbox("Tipo", list(TYPE_FILTER), key="f_type", label_visibility="collapsed")
    d1, d2, d3 = st.columns(3)
    category = d1.selectbox("Categoria", options, key="f_cat")
    start = d2.date_input("De", value=None, key="f_from", format="DD/MM/YYYY")
    end = d3.date_input("Até", value=None, key="f_to", format="DD/MM/YYYY")
    if start and end and end < start:
        st.warning("A data final é anterior à inicial.")
        return []
    return filter_transactions(items, tx_type=TYPE_FILTER[kind], search=search,
                               category=None if category == "Todas" else category,
                               date_from=start, date_to=end)


def render_dashboard(user) -> None:
    state = st.session_state
    head, menu = st.columns([4, 1.4], vertical_alignment="center")
    head.markdown('<div class="ff-brand"><span class="ff-logo">◆</span> Finance Flow</div>', unsafe_allow_html=True)
    with menu.popover(f"👤 {user.name.split()[0]}", use_container_width=True):
        st.text(user.name)
        st.caption(user.email)
        st.button("Sair da conta", key="logout_btn", use_container_width=True,
                  on_click=lambda: logout(st.session_state))

    st.markdown(
        '<div class="ff-dashboard-intro">'
        '<span class="ff-eyebrow">SEU RESUMO FINANCEIRO</span>'
        '<h1>Mais clareza para o seu dinheiro.</h1>'
        '<p>Receitas, despesas e planos em um só lugar.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    if msg := state.pop("flash", None):
        st.toast(msg, icon="✅")
    if err := state.pop("flash_error", None):
        st.error(err)

    try:
        all_items = list_transactions(user.uid)
    except TransactionError as exc:
        st.error(str(exc))
        return

    render_summary(summarize(all_items))  # totais SEMPRE globais (não dependem dos filtros)

    tab_list, tab_chart = st.tabs(["Movimentações", "Gráfico"])
    with tab_list:
        if not all_items:
            render_empty_state()
        else:
            filtered = _filters(all_items)
            if not filtered:
                st.info("Nenhuma movimentação encontrada com esses filtros.")
            else:
                st.download_button("Exportar CSV", to_csv(filtered), "finance-flow.csv", "text/csv",
                                   key="export_csv", icon=":material/download:")
                render_transaction_list(
                    filtered, on_edit=lambda tx: open_form(st.session_state, tx),
                    on_delete_request=_request_delete,
                    on_delete_confirm=lambda: _confirm_delete(user.uid),
                    on_delete_cancel=_cancel_delete, pending_delete=state.get("confirm_delete"), on_more=_more)
    with tab_chart:
        _render_chart(all_items)

    render_fab(lambda: open_form(st.session_state))
