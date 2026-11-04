from datetime import date

import pytest

from services.transactions import (AuthorizationError, NotFoundError, StorageError, ValidationError,
                                   calculate_totals, create_expense, create_income, create_transaction,
                                   delete_transaction, get_transaction, list_transactions, update_transaction)
from tests.fakes import BrokenFirestore, FakeFirestore
from views.transaction_form import CUSTOM, close_form, open_form, save_form

INC = {"description": "Salário", "amount_cents": 200000, "category": "Salário", "date": "2026-10-01"}
EXP = {"description": "Mercado", "amount_cents": 35000, "category": "Alimentação", "date": "2026-10-02"}


def test_cadastro_receita_e_despesa(db):
    create_income("u1", INC, db=db)
    create_expense("u1", EXP, db=db)
    assert {t["type"] for t in list_transactions("u1", db=db)} == {"income", "expense"}


def test_persistencia_apos_reiniciar_conexao(db):
    tx_id = create_income("u1", INC, db=db)
    nova_conexao = FakeFirestore(store=db.store)
    assert get_transaction("u1", tx_id, db=nova_conexao)["amount_cents"] == 200000


def test_exclusao(db):
    tx_id = create_income("u1", INC, db=db)
    delete_transaction("u1", tx_id, db=db)
    assert list_transactions("u1", db=db) == []


def test_edicao_atualiza_indicadores(db):
    tx_id = create_income("u1", INC, db=db)
    create_expense("u1", EXP, db=db)
    update_transaction("u1", tx_id, {**INC, "type": "income", "amount_cents": 300000}, db=db)
    assert calculate_totals("u1", db=db).balance_cents == 300000 - 35000
    assert "updated_at" in get_transaction("u1", tx_id, db=db)
    delete_transaction("u1", tx_id, db=db)
    assert calculate_totals("u1", db=db).balance_cents == -35000


@pytest.mark.parametrize("override", [
    {"amount_cents": 0}, {"amount_cents": -10}, {"amount_cents": 10.5}, {"amount_cents": True},
    {"description": "  "}, {"category": ""}, {"type": "xyz"}, {"date": "não-é-data"},
])
def test_rejeita_valores_invalidos(db, override):
    with pytest.raises(ValidationError):
        create_transaction("u1", {**INC, "type": "income", **override}, db=db)
    assert list_transactions("u1", db=db) == []


def test_criacao_idempotente_sem_duplicatas(db):
    create_transaction("u1", {**INC, "type": "income"}, tx_id="abc", db=db)
    create_transaction("u1", {**INC, "type": "income"}, tx_id="abc", db=db)
    assert len(list_transactions("u1", db=db)) == 1


def test_isolamento_entre_usuarios(db):
    id_a = create_income("A", INC, db=db)
    create_expense("B", EXP, db=db)
    assert [t["id"] for t in list_transactions("A", db=db)] == [id_a]
    assert calculate_totals("A", db=db).expense_cents == 0
    assert calculate_totals("B", db=db).income_cents == 0


def test_nao_altera_nem_exclui_transacao_de_outro_usuario(db):
    id_a = create_income("A", INC, db=db)
    with pytest.raises(NotFoundError):
        update_transaction("B", id_a, {**INC, "type": "income", "amount_cents": 1}, db=db)
    with pytest.raises(NotFoundError):
        delete_transaction("B", id_a, db=db)
    with pytest.raises(NotFoundError):
        get_transaction("B", id_a, db=db)
    with pytest.raises(AuthorizationError):  # tentativa de sobrescrever doc alheio via mesmo id
        create_transaction("B", {**INC, "type": "income"}, tx_id=id_a, db=db)
    assert get_transaction("A", id_a, db=db)["amount_cents"] == 200000


def test_sem_identidade_nao_acessa_dados(db):
    for uid in (None, "", "  "):
        with pytest.raises(AuthorizationError):
            list_transactions(uid, db=db)


def test_falha_de_gravacao_nao_finge_sucesso():
    state = {}
    open_form(state)
    state.update(form_desc="X", form_amount=1.0)
    from services.transactions import TransactionError
    with pytest.raises((RuntimeError, TransactionError, StorageError)):
        save_form(state, "u1", db=BrokenFirestore())


# ---- fluxo do formulário / navegação ----
def _preencher(state, **kw):
    state.update(form_type="income", form_desc="Salário", form_amount=2000.0, form_cat="Salário",
                 form_date=date(2026, 10, 1), **kw)


def test_salvar_volta_para_listagem_e_nao_duplica(db):
    state = {}
    open_form(state)
    assert state["view"] == "form"
    _preencher(state)
    assert save_form(state, "u1", db=db) is True
    assert state["view"] == "dashboard" and "form_id" not in state
    assert save_form(state, "u1", db=db) is False  # rerun/duplo clique: nada é gravado
    items = list_transactions("u1", db=db)
    assert len(items) == 1 and items[0]["amount_cents"] == 200000


def test_categoria_personalizada_e_edicao(db):
    state = {}
    open_form(state)
    _preencher(state, form_custom="Bicos")
    state["form_cat"] = CUSTOM
    save_form(state, "u1", db=db)
    tx = list_transactions("u1", db=db)[0]
    assert tx["category"] == "Bicos"
    open_form(state, tx)
    assert state["form_cat"] == CUSTOM and state["form_custom"] == "Bicos"
    state["form_amount"] = 2500.5
    assert save_form(state, "u1", db=db)
    assert list_transactions("u1", db=db)[0]["amount_cents"] == 250050


def test_valor_zero_mostra_erro_e_permanece_no_formulario(db):
    state = {}
    open_form(state)
    _preencher(state)
    state["form_amount"] = 0.0
    assert save_form(state, "u1", db=db) is False
    assert state["view"] == "form" and "maior que zero" in state["form_error"]
    assert list_transactions("u1", db=db) == []


def test_cancelar_nao_grava(db):
    state = {}
    open_form(state)
    _preencher(state)
    close_form(state)
    assert state["view"] == "dashboard"
    assert list_transactions("u1", db=db) == []
