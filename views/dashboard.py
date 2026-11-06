"""Tela principal: indicadores, movimentações (+ gráfico) e botão +."""
from __future__ import annotations

from datetime import date
from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from components.floating_button import render_fab
from components.summary_cards import render_summary
from components.transaction_list import PAGE_SIZE, render_empty_state, render_transaction_list
from services.auth import logout
from services.export import monthly_summary_csv, to_csv
from services.planning import (PlanningError, add_savings_goal, delete_budget, delete_savings_goal,
                               list_budgets, list_savings_goals, set_budget, update_savings_goal)
from services.transactions import (CATEGORIES, EXPENSE, INCOME, TYPE_LABELS, TransactionError, delete_transaction,
                                   filter_transactions, list_transactions, summarize)
from utils.formatting import format_brl, format_date_br, reais_to_cents
from views.transaction_form import open_form

TYPE_FILTER = {"Todas": None, "Receitas": INCOME, "Despesas": EXPENSE}
NAVIGATION = ("Visão geral", "Movimentações", "Análises", "Planejamento")
CHART_PERIODS = {"Últimos 3 meses": 3, "Últimos 6 meses": 6,
                 "Últimos 12 meses": 12, "Todo o período": None}


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


def _transaction_frame(items) -> pd.DataFrame:
    df = pd.DataFrame(items)
    df["Data"] = pd.to_datetime(df["date"])
    df["Mês"] = df["Data"].dt.to_period("M").astype(str)
    df["Valor"] = df["amount_cents"] / 100
    df["Tipo"] = df["type"].map(TYPE_LABELS)
    return df


def _chart_layout(fig, *, legend=True) -> None:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=16, b=0),
        font=dict(color="#bfdbfe"),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="rgba(96, 165, 250, .16)", tickprefix="R$ "),
        showlegend=legend,
        legend_title_text="",
    )


def _render_monthly_chart(items) -> None:
    if not items:
        st.info("Adicione movimentações para acompanhar sua evolução financeira.")
        return
    df = _transaction_frame(items)
    grouped = df.groupby(["Mês", "Tipo"], as_index=False)["Valor"].sum()
    fig = px.bar(grouped, x="Mês", y="Valor", color="Tipo", barmode="group",
                 color_discrete_map={"Receita": "#60a5fa", "Despesa": "#cbd5e1"})
    _chart_layout(fig)
    st.plotly_chart(fig, use_container_width=True)


def _render_expense_chart(items) -> None:
    expenses = [item for item in items if item["type"] == EXPENSE]
    if not expenses:
        st.info("Suas despesas por categoria aparecerão aqui.")
        return
    df = pd.DataFrame(expenses)
    df["Valor"] = df["amount_cents"] / 100
    grouped = df.groupby("category", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)
    fig = px.pie(grouped, names="category", values="Valor", hole=.68,
                 color_discrete_sequence=["#3b82f6", "#93c5fd", "#1d4ed8", "#bfdbfe",
                                          "#60a5fa", "#64748b", "#dbeafe", "#2563eb"])
    fig.update_traces(textposition="inside", textinfo="percent")
    _chart_layout(fig, legend=False)
    st.plotly_chart(fig, use_container_width=True)


def _period_items(items, period: str) -> list[dict]:
    months = CHART_PERIODS[period]
    if months is None:
        return items
    today = date.today()
    month_index = today.year * 12 + today.month - 1 - months + 1
    start = date(month_index // 12, month_index % 12 + 1, 1).isoformat()
    return [item for item in items if item["date"] >= start]


def _render_monthly_export(items) -> None:
    today = date.today()
    month_items = [item for item in items if item["date"][:7] == today.strftime("%Y-%m")]
    filename = f"nexo-financeiro-resumo-{today:%Y-%m}.csv"
    st.download_button(
        "Baixar resumo do mês (CSV)",
        monthly_summary_csv(month_items, today.year, today.month),
        filename,
        "text/csv",
        key="monthly_summary_csv",
        icon=":material/download:",
    )


def _month_totals(items, year: int, month: int) -> tuple[int, int, int]:
    totals = [item for item in items
              if (parsed := date.fromisoformat(item["date"])).year == year and parsed.month == month]
    income = sum(item["amount_cents"] for item in totals if item["type"] == INCOME)
    expense = sum(item["amount_cents"] for item in totals if item["type"] == EXPENSE)
    return income, expense, len(totals)


def _render_month_highlights(items) -> None:
    today = date.today()
    current_income, current_expense, current_count = _month_totals(items, today.year, today.month)
    previous_month = today.month - 1 or 12
    previous_year = today.year if today.month > 1 else today.year - 1
    _, previous_expense, _ = _month_totals(items, previous_year, previous_month)
    expense_delta = None
    if previous_expense:
        expense_delta = (current_expense - previous_expense) / previous_expense * 100
    columns = st.columns(3)
    columns[0].metric("Receitas neste mês", format_brl(current_income))
    columns[1].metric("Despesas neste mês", format_brl(current_expense),
                      delta=f"{expense_delta:+.0f}% vs. mês anterior" if expense_delta is not None else None,
                      delta_color="inverse")
    columns[2].metric("Lançamentos no mês", current_count)


def _render_recent(items) -> None:
    st.subheader("Movimentações recentes")
    if not items:
        render_empty_state()
        return
    rows = []
    for item in items[:5]:
        positive = item["type"] == INCOME
        amount = format_brl(item["amount_cents"] if positive else -item["amount_cents"])
        sign = "+" if positive else "−"
        color = "var(--income)" if positive else "var(--expense)"
        rows.append(
            '<div class="ff-recent-row">'
            f'<span class="ff-recent-dot {"ff-recent-income" if positive else "ff-recent-expense"}"></span>'
            f'<div class="ff-recent-main"><strong>{escape(item["description"])}</strong>'
            f'<span>{escape(item["category"])} · {format_date_br(item["date"])}</span></div>'
            f'<strong style="color:{color}">{sign} {amount}</strong></div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def _render_budget_planner(uid: str, items: list[dict]) -> None:
    st.subheader("Orçamentos mensais por categoria")
    try:
        budgets = list_budgets(uid)
    except PlanningError as exc:
        st.error(str(exc))
        return

    expense_categories = {item["category"] for item in items if item["type"] == EXPENSE}
    expense_categories.update(budget["category"] for budget in budgets)
    options = sorted(set(CATEGORIES[EXPENSE]) | expense_categories, key=str.casefold)
    with st.form("budget_form"):
        category = st.selectbox("Categoria", options, key="budget_category")
        amount = st.number_input("Limite mensal (R$)", min_value=0.01, step=50.0,
                                 format="%.2f", key="budget_amount")
        submitted = st.form_submit_button("Salvar orçamento", type="primary")
    if submitted:
        try:
            set_budget(uid, category, reais_to_cents(amount))
        except (PlanningError, ValueError) as exc:
            st.error(str(exc) if isinstance(exc, PlanningError) else "Informe um valor válido.")
        else:
            st.toast("Orçamento salvo.")
            st.rerun()

    if not budgets:
        st.info("Defina um limite mensal para começar a acompanhar suas categorias.")
        return
    today = date.today()
    monthly_expenses = [
        item for item in items
        if item["type"] == EXPENSE and item["date"][:7] == today.strftime("%Y-%m")
    ]
    for budget in budgets:
        spent = sum(item["amount_cents"] for item in monthly_expenses
                    if item["category"] == budget["category"])
        limit = budget["amount_cents"]
        st.markdown(f"**{escape(budget['category'])}**")
        st.progress(min(spent / limit, 1.0))
        used_percent = spent / limit * 100
        st.caption(f"{format_brl(spent)} de {format_brl(limit)} · {used_percent:.0f}% utilizado")
        if spent > limit:
            st.warning(f"Você ultrapassou o orçamento de {escape(budget['category'])}.")
        with st.popover("Remover orçamento", key=f"remove_budget_{budget['id']}"):
            st.warning(f"Remover o orçamento de {escape(budget['category'])}?")
            if st.button("Confirmar remoção", key=f"confirm_budget_{budget['id']}"):
                try:
                    delete_budget(uid, budget["id"])
                except PlanningError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()


def _render_savings_goals(uid: str) -> None:
    st.subheader("Metas de economia")
    try:
        goals = list_savings_goals(uid)
    except PlanningError as exc:
        st.error(str(exc))
        return

    with st.form("goal_form", clear_on_submit=True):
        name = st.text_input("Nome da meta", max_chars=80, placeholder="Ex.: Viagem de férias")
        target = st.number_input("Valor desejado (R$)", min_value=0.01, step=100.0,
                                 format="%.2f", key="goal_target")
        submitted = st.form_submit_button("Criar meta", type="primary")
    if submitted:
        try:
            add_savings_goal(uid, name, reais_to_cents(target))
        except (PlanningError, ValueError) as exc:
            st.error(str(exc) if isinstance(exc, PlanningError) else "Informe um valor válido.")
        else:
            st.toast("Meta criada.")
            st.rerun()

    if not goals:
        st.info("Crie uma meta para acompanhar seu progresso de economia.")
        return
    for goal in goals:
        target_cents = goal["target_cents"]
        saved_cents = goal["saved_cents"]
        st.markdown(f"**{escape(goal['name'])}**")
        st.progress(min(saved_cents / target_cents, 1.0))
        st.caption(f"{format_brl(saved_cents)} guardados de {format_brl(target_cents)} · "
                   f"{saved_cents / target_cents * 100:.0f}%")
        with st.form(f"goal_progress_{goal['id']}"):
            saved = st.number_input(
                "Total já guardado (R$)",
                min_value=0.0,
                value=saved_cents / 100,
                step=50.0,
                format="%.2f",
                key=f"saved_{goal['id']}",
            )
            update = st.form_submit_button("Atualizar progresso")
        if update:
            try:
                update_savings_goal(uid, goal["id"], reais_to_cents(saved))
            except (PlanningError, ValueError) as exc:
                st.error(str(exc) if isinstance(exc, PlanningError) else "Informe um valor válido.")
            else:
                st.toast("Progresso atualizado.")
                st.rerun()
        with st.popover("Excluir meta", key=f"remove_goal_{goal['id']}"):
            st.warning(f"Excluir a meta {escape(goal['name'])}?")
            if st.button("Confirmar exclusão", key=f"confirm_goal_{goal['id']}"):
                try:
                    delete_savings_goal(uid, goal["id"])
                except PlanningError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()


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
    with st.sidebar:
        initials = "".join(part[0] for part in user.name.split()[:2]).upper()
        st.markdown(
            '<div class="ff-sidebar-profile">'
            f'<span class="ff-avatar">{escape(initials)}</span>'
            f'<span class="ff-profile-info"><strong>{escape(user.name)}</strong>'
            f'<small>{escape(user.email)}</small></span></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="ff-sidebar-section-label">NAVEGAÇÃO</div>', unsafe_allow_html=True)
        page = st.radio(
            "Navegação", NAVIGATION, key="dashboard_page", label_visibility="collapsed",
        )
        st.button("＋  Nova movimentação", key="sidebar_add", type="primary", use_container_width=True,
                  on_click=lambda: open_form(st.session_state))
        st.button("Sair da conta", key="logout_btn", use_container_width=True,
                  on_click=lambda: logout(st.session_state))

    page_titles = {
        "Visão geral": ("SEU RESUMO FINANCEIRO", "Mais clareza para o seu dinheiro.",
                        "Acompanhe o que entra, o que sai e como seu mês está indo."),
        "Movimentações": ("SEU HISTÓRICO", "Todas as movimentações.",
                          "Busque, filtre, edite e exporte seus lançamentos."),
        "Análises": ("SEUS RELATÓRIOS", "Entenda seus hábitos.",
                     "Visualize tendências e descubra para onde seu dinheiro está indo."),
        "Planejamento": ("SEUS PLANOS", "Planeje com mais intenção.",
                         "Defina limites para os gastos e acompanhe suas metas de economia."),
    }
    eyebrow, title, subtitle = page_titles[page]
    st.markdown(
        f'<div class="ff-dashboard-intro"><span class="ff-eyebrow">{eyebrow}</span>'
        f'<h1>{title}</h1><p>{subtitle}</p></div>',
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

    render_summary(summarize(all_items))

    if page == "Visão geral":
        _render_month_highlights(all_items)
        _render_monthly_export(all_items)
        chart_month_items = [item for item in all_items
                             if item["date"][:7] == date.today().strftime("%Y-%m")]
        chart, pie = st.columns([1.5, 1], gap="large")
        with chart:
            st.subheader("Receitas e despesas ao longo do tempo")
            _render_monthly_chart(all_items)
        with pie:
            st.subheader("Despesas por categoria neste mês")
            _render_expense_chart(chart_month_items)
        _render_recent(all_items)
    elif page == "Movimentações":
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
    elif page == "Análises":
        _render_month_highlights(all_items)
        period = st.selectbox("Período dos gráficos", list(CHART_PERIODS), key="chart_period")
        chart_items = _period_items(all_items, period)
        left, right = st.columns([1.5, 1], gap="large")
        with left:
            st.subheader("Fluxo mensal")
            _render_monthly_chart(chart_items)
        with right:
            st.subheader("Despesas por categoria")
            _render_expense_chart(chart_items)
        _render_monthly_export(all_items)
    else:
        _render_budget_planner(user.uid, all_items)
        st.divider()
        _render_savings_goals(user.uid)

    render_fab(lambda: open_form(st.session_state))
