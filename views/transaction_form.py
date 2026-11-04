"""Tela de cadastro/edição de movimentação."""
from __future__ import annotations

import uuid
from datetime import date

import streamlit as st

from services.transactions import (CATEGORIES, EXPENSE, INCOME, TYPE_LABELS, TransactionError,
                                   ValidationError, create_transaction, update_transaction)
from utils.formatting import reais_to_cents

CUSTOM = "Outra (personalizada)"
FORM_KEYS = ("form_id", "form_editing", "form_type", "form_desc", "form_amount",
             "form_cat", "form_custom", "form_date", "form_notes", "form_error")


def open_form(state, tx: dict | None = None) -> None:
    """Abre o formulário (novo ou edição). O `form_id` torna o salvamento idempotente."""
    if tx:
        category, custom = tx["category"], ""
        if category not in CATEGORIES[tx["type"]]:
            category, custom = CUSTOM, tx["category"]
        state.update(form_editing=tx["id"], form_type=tx["type"], form_desc=tx["description"],
                     form_amount=tx["amount_cents"] / 100, form_cat=category, form_custom=custom,
                     form_date=date.fromisoformat(tx["date"]), form_notes=tx.get("notes", ""))
    else:
        state.update(form_editing=None, form_type=EXPENSE, form_desc="", form_amount=0.0,
                     form_cat=CATEGORIES[EXPENSE][0], form_custom="", form_date=date.today(), form_notes="")
    state.update(form_id=uuid.uuid4().hex, form_error=None, view="form")


def close_form(state) -> None:
    for key in FORM_KEYS:
        state.pop(key, None)
    state["view"] = "dashboard"


def build_payload(state) -> dict:
    category = state.get("form_cat")
    if category == CUSTOM:
        category = (state.get("form_custom") or "").strip()
        if not category:
            raise ValidationError("Informe o nome da categoria personalizada.")
    try:
        cents = reais_to_cents(state.get("form_amount") or 0)
    except ValueError as exc:
        raise ValidationError("Valor inválido.") from exc
    return {"type": state.get("form_type"), "description": state.get("form_desc"),
            "amount_cents": cents, "category": category, "date": state.get("form_date"),
            "notes": state.get("form_notes")}


def save_form(state, uid: str, db=None) -> bool:
    """Valida, grava e volta à listagem. Chamadas repetidas não duplicam registros."""
    form_id, editing = state.get("form_id"), state.get("form_editing")
    if not form_id:
        state["view"] = "dashboard"
        return False
    try:
        payload = build_payload(state)
        if editing:
            update_transaction(uid, editing, payload, db=db)
        else:
            create_transaction(uid, payload, tx_id=form_id, db=db)
    except TransactionError as exc:
        state["form_error"] = str(exc)
        return False
    close_form(state)
    state["flash"] = "Movimentação atualizada." if editing else "Movimentação salva com sucesso."
    return True


def render_form(user) -> None:
    state = st.session_state
    if "form_id" not in state:
        open_form(state)
    editing = bool(state.get("form_editing"))
    st.markdown(f'<div class="ff-brand"><span class="ff-logo">◆</span> Finance Flow</div>'
                f'<h2 class="ff-title">{"Editar movimentação" if editing else "Nova movimentação"}</h2>',
                unsafe_allow_html=True)
    with st.container(key="form_card"):
        st.radio("Tipo de movimentação", [INCOME, EXPENSE], key="form_type",
                 format_func=TYPE_LABELS.get, horizontal=True)
        options = CATEGORIES[state["form_type"]] + [CUSTOM]
        if state.get("form_cat") not in options:
            state["form_cat"] = options[0]
        st.text_input("Descrição", key="form_desc", max_chars=120, placeholder="Ex.: Mercado do mês")
        st.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f", key="form_amount")
        st.selectbox("Categoria", options, key="form_cat")
        if state["form_cat"] == CUSTOM:
            st.text_input("Nome da categoria", key="form_custom", max_chars=40)
        st.date_input("Data", key="form_date", format="DD/MM/YYYY")
        st.text_area("Observações (opcional)", key="form_notes", max_chars=500)
        if state.get("form_error"):
            st.error(state["form_error"])
        save, cancel = st.columns(2)
        save.button("Salvar movimentação", key="form_save", type="primary", use_container_width=True,
                    on_click=lambda: save_form(st.session_state, user.uid))
        cancel.button("Cancelar", key="form_cancel", use_container_width=True,
                      on_click=lambda: close_form(st.session_state))
