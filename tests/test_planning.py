import pytest

from services.planning import (
    PlanningAuthorizationError,
    PlanningNotFoundError,
    PlanningValidationError,
    add_savings_goal,
    delete_budget,
    delete_savings_goal,
    list_budgets,
    list_savings_goals,
    set_budget,
    update_savings_goal,
)


def test_orcamentos_ficam_isolados_e_sao_atualizados(db):
    budget_id = set_budget("u1", "Alimentação", 50000, db=db)
    set_budget("u1", "Alimentação", 75000, db=db)
    set_budget("u2", "Alimentação", 30000, db=db)

    budgets = list_budgets("u1", db=db)
    assert len(budgets) == 1
    assert budgets[0]["id"] == budget_id
    assert budgets[0]["amount_cents"] == 75000
    assert list_budgets("u2", db=db)[0]["amount_cents"] == 30000


def test_meta_de_economia_pode_ser_atualizada_e_excluida(db):
    goal_id = add_savings_goal("u1", "Viagem", 300000, db=db)
    update_savings_goal("u1", goal_id, 125000, db=db)

    goal = list_savings_goals("u1", db=db)[0]
    assert (goal["name"], goal["target_cents"], goal["saved_cents"]) == ("Viagem", 300000, 125000)
    delete_savings_goal("u1", goal_id, db=db)
    assert list_savings_goals("u1", db=db) == []


def test_planejamento_nao_pode_ser_acessado_por_outro_usuario(db):
    budget_id = set_budget("u1", "Lazer", 10000, db=db)
    goal_id = add_savings_goal("u1", "Notebook", 100000, db=db)

    with pytest.raises(PlanningNotFoundError):
        delete_budget("u2", budget_id, db=db)
    with pytest.raises(PlanningNotFoundError):
        update_savings_goal("u2", goal_id, 5000, db=db)
    with pytest.raises(PlanningNotFoundError):
        delete_savings_goal("u2", goal_id, db=db)
    assert list_budgets("u1", db=db)[0]["amount_cents"] == 10000
    assert list_savings_goals("u1", db=db)[0]["saved_cents"] == 0


@pytest.mark.parametrize("category,amount", [("", 100), ("Alimentação", 0), ("Alimentação", -1),
                                              ("Alimentação", True), ("a" * 41, 100)])
def test_orcamento_rejeita_dados_invalidos(db, category, amount):
    with pytest.raises(PlanningValidationError):
        set_budget("u1", category, amount, db=db)


@pytest.mark.parametrize("name,target", [("", 100), ("x" * 81, 100), ("Meta", 0), ("Meta", True)])
def test_meta_rejeita_dados_invalidos(db, name, target):
    with pytest.raises(PlanningValidationError):
        add_savings_goal("u1", name, target, db=db)
