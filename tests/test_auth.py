import pytest

from services import auth
from services.auth import AuthError, AuthSession
from services.transactions import create_income, list_transactions
from tests.fakes import BrokenFirestore, FakeFirestore


class FakeIdentity:
    """Simula Firebase Authentication (REST + Admin)."""
    def __init__(self):
        self.users, self.deleted, self.reset_sent = {}, [], []

    def post(self, endpoint, payload, form=False):
        def fail(code):
            raise AuthError(auth._friendly(code), code=code)
        if endpoint == auth.SIGN_UP:
            if payload["email"] in self.users:
                fail("EMAIL_EXISTS")
            uid = f"uid{len(self.users) + 1}"
            self.users[payload["email"]] = (payload["password"], uid)
            return {"idToken": f"tok-{uid}", "refreshToken": f"ref-{uid}", "localId": uid}
        if endpoint == auth.SIGN_IN:
            pwd_uid = self.users.get(payload["email"])
            if not pwd_uid or pwd_uid[0] != payload["password"]:
                fail("INVALID_LOGIN_CREDENTIALS")
            uid = pwd_uid[1]
            return {"idToken": f"tok-{uid}", "refreshToken": f"ref-{uid}", "localId": uid}
        if endpoint == auth.SEND_OOB:
            if payload["email"] not in self.users:
                fail("EMAIL_NOT_FOUND")
            self.reset_sent.append(payload["email"])
            return {}
        if endpoint == auth.REFRESH:
            uid = payload["refresh_token"].removeprefix("ref-")
            if uid not in [u for _, u in self.users.values()]:
                fail("INVALID_REFRESH_TOKEN")
            return {"id_token": f"tok-{uid}", "refresh_token": payload["refresh_token"]}
        raise AssertionError(endpoint)

    def verify(self, token):
        if token.startswith("tok-"):
            return {"uid": token.removeprefix("tok-")}
        raise auth.TokenError("invalid")

    def delete(self, uid):
        self.deleted.append(uid)


@pytest.fixture
def idp(monkeypatch):
    fake = FakeIdentity()
    monkeypatch.setattr(auth, "_post", fake.post)
    monkeypatch.setattr(auth, "_verify_id_token", fake.verify)
    monkeypatch.setattr(auth, "_admin_delete_user", fake.delete)
    return fake


def test_cadastro_valido_cria_conta_e_perfil(idp, db):
    session = auth.sign_up("Ana Souza", "Ana@Email.com", "segredo123", "segredo123", db=db)
    assert session.uid == "uid1" and session.email == "ana@email.com"
    profile = auth.get_profile("uid1", db=db)
    assert profile["name"] == "Ana Souza" and profile["uid"] == "uid1"
    assert "password" not in profile and "segredo123" not in str(db.store)


@pytest.mark.parametrize("args", [
    ("", "a@a.com", "123456", "123456"), ("Ana", "invalido", "123456", "123456"),
    ("Ana", "a@a.com", "123", "123"), ("Ana", "a@a.com", "123456", "654321"),
])
def test_cadastro_rejeita_dados_invalidos(idp, db, args):
    with pytest.raises(AuthError):
        auth.sign_up(*args, db=db)
    assert idp.users == {}


def test_email_ja_cadastrado(idp, db):
    auth.sign_up("Ana", "a@a.com", "123456", "123456", db=db)
    with pytest.raises(AuthError, match="já está cadastrado"):
        auth.sign_up("Ana 2", "a@a.com", "123456", "123456", db=db)


def test_falha_no_perfil_desfaz_conta(idp):
    with pytest.raises(AuthError, match="concluir o cadastro"):
        auth.sign_up("Ana", "a@a.com", "123456", "123456", db=BrokenFirestore())
    assert idp.deleted == ["uid1"]


def test_login_valido_e_invalido(idp, db):
    auth.sign_up("Ana Souza", "a@a.com", "123456", "123456", db=db)
    session = auth.sign_in("a@a.com", "123456", db=db)
    assert session.name == "Ana Souza" and session.uid == "uid1"
    with pytest.raises(AuthError, match="incorretos"):
        auth.sign_in("a@a.com", "errada", db=db)
    with pytest.raises(AuthError, match="incorretos"):
        auth.sign_in("naoexiste@a.com", "123456", db=db)  # mesma mensagem: sem enumeração
    with pytest.raises(AuthError):
        auth.sign_in("", "", db=db)


def test_recuperacao_de_senha_nao_revela_se_email_existe(idp, db):
    auth.sign_up("Ana", "a@a.com", "123456", "123456", db=db)
    assert auth.send_password_reset("a@a.com") == auth.GENERIC_RESET_MESSAGE
    assert auth.send_password_reset("outro@a.com") == auth.GENERIC_RESET_MESSAGE
    assert idp.reset_sent == ["a@a.com"]
    with pytest.raises(AuthError):
        auth.send_password_reset("invalido")


def test_sessao_valida_logout_e_bloqueio(idp, db):
    session = auth.sign_up("Ana", "a@a.com", "123456", "123456", db=db)
    state = {auth.SESSION_KEY: session.to_dict(), "view": "dashboard"}
    assert auth.authenticate(state).uid == "uid1"
    assert "123456" not in str(state)  # senha nunca vai para o estado
    auth.logout(state)
    assert state == {} and auth.authenticate(state) is None


def test_token_expirado_e_renovado_e_invalido_bloqueia(idp, db):
    session = auth.sign_up("Ana", "a@a.com", "123456", "123456", db=db)
    expirada = AuthSession(session.uid, session.email, session.name, "expirado", session.refresh_token)
    state = {auth.SESSION_KEY: expirada.to_dict()}
    assert auth.authenticate(state).uid == "uid1"
    assert state[auth.SESSION_KEY]["id_token"] == "tok-uid1"
    forjada = AuthSession("uid-alheio", "x@x.com", "X", "token-falso", "refresh-falso")
    state = {auth.SESSION_KEY: forjada.to_dict()}
    assert auth.authenticate(state) is None and auth.SESSION_KEY not in state


def test_uid_vem_do_token_verificado_e_nao_da_sessao(idp, db):
    a = auth.sign_up("Ana", "a@a.com", "123456", "123456", db=db)
    forjada = AuthSession("uid-de-outra-pessoa", a.email, a.name, a.id_token, a.refresh_token)
    assert auth.authenticate({auth.SESSION_KEY: forjada.to_dict()}).uid == "uid1"


def test_isolamento_e_indicadores_por_conta(idp, db):
    a = auth.sign_up("Ana", "a@a.com", "123456", "123456", db=db)
    b = auth.sign_up("Beto", "b@b.com", "123456", "123456", db=db)
    create_income(a.uid, {"description": "x", "amount_cents": 1000, "category": "Outros", "date": "2026-10-01"}, db=db)
    assert len(list_transactions(a.uid, db=db)) == 1 and list_transactions(b.uid, db=db) == []
