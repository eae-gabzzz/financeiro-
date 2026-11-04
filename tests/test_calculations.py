from datetime import date

from services.transactions import (EXPENSE, INCOME, calculate_totals, create_expense, create_income,
                                   filter_transactions, list_transactions, summarize)
from utils.formatting import format_brl, reais_to_cents


def test_format_brl():
    assert format_brl(123456) == "R$ 1.234,56"
    assert format_brl(0) == "R$ 0,00"
    assert format_brl(5) == "R$ 0,05"
    assert format_brl(-35000) == "-R$ 350,00"


def test_reais_to_cents_sem_erro_de_float():
    assert reais_to_cents(19.99) == 1999
    assert reais_to_cents(0.1 + 0.2) == 30
    assert reais_to_cents("1.234,56".replace(".", "")) == 123456


def test_totais_receita_despesa_saldo(db):
    create_income("u1", {"description": "Salário", "amount_cents": 200000, "category": "Salário", "date": "2026-10-01"}, db=db)
    create_expense("u1", {"description": "Mercado", "amount_cents": 35000, "category": "Alimentação", "date": "2026-10-02"}, db=db)
    totals = calculate_totals("u1", db=db)
    assert format_brl(totals.income_cents) == "R$ 2.000,00"
    assert format_brl(totals.expense_cents) == "R$ 350,00"
    assert format_brl(totals.balance_cents) == "R$ 1.650,00"


def test_sem_transacoes_totais_zerados(db):
    totals = calculate_totals("u1", db=db)
    assert (totals.income_cents, totals.expense_cents, totals.balance_cents) == (0, 0, 0)


def test_filtros_nao_alteram_totais_globais(db):
    create_income("u1", {"description": "Salário", "amount_cents": 200000, "category": "Salário", "date": "2026-10-01"}, db=db)
    create_expense("u1", {"description": "Mercado", "amount_cents": 35000, "category": "Alimentação", "date": "2026-09-02"}, db=db)
    items = list_transactions("u1", db=db)
    antes = summarize(items)
    assert len(filter_transactions(items, tx_type=EXPENSE)) == 1
    assert len(filter_transactions(items, tx_type=INCOME)) == 1
    assert len(filter_transactions(items, search="merca")) == 1
    assert len(filter_transactions(items, category="Salário")) == 1
    assert len(filter_transactions(items, date_from=date(2026, 10, 1))) == 1
    assert len(filter_transactions(items, date_to=date(2026, 9, 30))) == 1
    assert summarize(items) == antes
    assert calculate_totals("u1", db=db) == antes


def test_ordem_mais_recente_primeiro(db):
    for d in ("2026-01-01", "2026-03-01", "2026-02-01"):
        create_income("u1", {"description": d, "amount_cents": 100, "category": "Outros", "date": d}, db=db)
    assert [t["date"] for t in list_transactions("u1", db=db)] == ["2026-03-01", "2026-02-01", "2026-01-01"]
