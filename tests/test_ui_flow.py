"""Teste ponta a ponta da interface (Streamlit AppTest) com Firebase simulado."""
import pytest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from database.firebase import FirebaseConfigError
from tests.fakes import FakeFirestore


APP = Path(__file__).resolve().parent.parent / "app.py"


def _html(at):
    return " ".join(m.value for m in at.markdown)


def test_sem_configuracao_mostra_erro_util(monkeypatch):
    def boom():
        raise FirebaseConfigError("Credenciais do Firebase não encontradas.")
    monkeypatch.setattr("database.firebase._load_config", boom)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert any("Firebase não configurado" in e.value for e in at.error)


def test_dashboard_protegido_sem_login(monkeypatch):
    monkeypatch.setattr("database.firebase.get_db", lambda: FakeFirestore())
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert "Entrar" in " ".join(b.label for b in at.button) or at.get("form_submit_button")
    assert "<div class=\"ff-cards\">" not in _html(at) and "Receita" not in " ".join(m.value for m in at.markdown if "<style>" not in m.value)


def test_fluxo_completo_receita_e_despesa(monkeypatch):
    fake = FakeFirestore()
    monkeypatch.setattr("database.firebase.get_db", lambda: fake)
    monkeypatch.setattr("services.auth._verify_id_token", lambda t: {"uid": "u1"})
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state["auth"] = {"uid": "u1", "email": "a@a.com", "name": "Ana Souza",
                                "id_token": "x", "refresh_token": "y"}
    at.run()
    assert not at.exception
    html = _html(at)
    assert all(w in html for w in ("Receita", "Despesas", "Saldo", "R$ 0,00", "Seu histórico financeiro começa aqui."))

    for tipo, desc, valor, esperado in (("income", "Salário", 2000.0, "R$ 2.000,00"),
                                        ("expense", "Mercado", 350.0, "R$ 1.650,00")):
        at.button(key="fab_btn").click().run()
        assert at.session_state["view"] == "form"
        at.radio(key="form_type").set_value(tipo).run()
        at.text_input(key="form_desc").set_value(desc)
        at.number_input(key="form_amount").set_value(valor)
        at.button(key="form_save").click().run()
        assert not at.exception
        assert at.session_state["view"] == "dashboard"
        assert esperado in _html(at) and desc in _html(at)
    assert len(fake.store["transactions"]) == 2
    assert all(t["user_id"] == "u1" for t in fake.store["transactions"].values())


def test_navegacao_lateral_e_graficos_de_analise(monkeypatch):
    from datetime import date

    today = date.today().isoformat()
    fake = FakeFirestore({
        "transactions": {
            "salary": {"user_id": "u1", "type": "income", "description": "Salário",
                       "amount_cents": 250000, "category": "Salário", "date": today},
            "groceries": {"user_id": "u1", "type": "expense", "description": "Mercado",
                          "amount_cents": 35000, "category": "Alimentação", "date": today},
        },
    })
    monkeypatch.setattr("database.firebase.get_db", lambda: fake)
    monkeypatch.setattr("services.auth._verify_id_token", lambda t: {"uid": "u1"})
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state["auth"] = {"uid": "u1", "email": "a@a.com", "name": "Ana Souza",
                                "id_token": "x", "refresh_token": "y"}
    at.run()

    assert not at.exception
    assert "Mercado" in _html(at)
    assert len(at.get("plotly_chart")) == 2

    at.radio(key="dashboard_page").set_value("Análises").run()
    assert not at.exception
    assert "Despesas por categoria" in " ".join(heading.value for heading in at.subheader)
    assert len(at.get("plotly_chart")) == 2
    assert "Período dos gráficos" in " ".join(element.label for element in at.selectbox)

    at.radio(key="dashboard_page").set_value("Planejamento").run()
    assert not at.exception
    assert "Orçamentos mensais por categoria" in " ".join(heading.value for heading in at.subheader)
    assert "Metas de economia" in " ".join(heading.value for heading in at.subheader)

    at.selectbox(key="budget_category").set_value("Alimentação")
    at.number_input(key="budget_amount").set_value(500.0)
    at.get("form_submit_button")[0].click().run()
    assert not at.exception
    assert len(fake.store["financial_plans"]) == 1

    at.text_input[0].set_value("Viagem")
    at.number_input(key="goal_target").set_value(3000.0)
    at.get("form_submit_button")[1].click().run()
    assert not at.exception
    assert len(fake.store["financial_plans"]) == 2
    assert any(plan.get("name") == "Viagem" for plan in fake.store["financial_plans"].values())


def test_barra_lateral_nao_exibe_botao_de_ia(monkeypatch):
    monkeypatch.setattr("database.firebase.get_db", lambda: FakeFirestore())
    monkeypatch.setattr("services.auth._verify_id_token", lambda t: {"uid": "u1"})
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state["auth"] = {"uid": "u1", "email": "a@a.com", "name": "Ana Souza",
                                "id_token": "x", "refresh_token": "y"}
    at.run()

    assert not at.exception
    assert "sidebar_ai" not in [button.key for button in at.button]
    assert all("IA local" not in button.label for button in at.button)
