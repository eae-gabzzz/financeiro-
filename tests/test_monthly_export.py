import csv
from io import StringIO

from services.export import monthly_summary_csv


def test_resumo_mensal_exporta_totais_e_categorias_sem_formulas():
    items = [
        {"date": "2026-11-02", "type": "income", "category": "Salário",
         "description": "Pagamento", "amount_cents": 250000},
        {"date": "2026-11-03", "type": "expense", "category": "Alimentação",
         "description": "Mercado", "amount_cents": 35000},
        {"date": "2026-11-04", "type": "expense", "category": "=1+1",
         "description": "Teste", "amount_cents": 10000},
        {"date": "2026-10-04", "type": "expense", "category": "Alimentação",
         "description": "Outro mês", "amount_cents": 50000},
    ]

    content = monthly_summary_csv(items, 2026, 11).decode("utf-8-sig")
    rows = list(csv.DictReader(StringIO(content), delimiter=";"))

    assert {"Receitas", "Despesas", "Saldo", "Lançamentos"} <= {row["Indicador"] for row in rows}
    assert next(row for row in rows if row["Indicador"] == "Receitas")["Valor (R$)"] == "2500,00"
    assert next(row for row in rows if row["Indicador"] == "Despesas")["Valor (R$)"] == "450,00"
    assert next(row for row in rows if row["Indicador"] == "Saldo")["Valor (R$)"] == "2050,00"
    assert "'=1+1" in content


def test_resumo_mensal_sem_movimentacoes():
    content = monthly_summary_csv([], 2026, 11).decode("utf-8-sig")
    assert "Saldo;0,00" in content
