"""Autenticação: Firebase Authentication (REST oficial) + validação no servidor (Admin SDK).

- Senhas só trafegam até o Firebase; nunca são salvas (Firestore, disco ou session_state).
- O UID usado nas operações vem SEMPRE de um ID token verificado pelo Admin SDK.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields

import requests
import streamlit as st
from google.cloud.firestore import SERVER_TIMESTAMP

from database.firebase import init_app, resolve_db

SESSION_KEY = "auth"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 6  # mínimo do Firebase Authentication
_IDT = "https://identitytoolkit.googleapis.com/v1/accounts"
SIGN_UP, SIGN_IN, SEND_OOB = f"{_IDT}:signUp", f"{_IDT}:signInWithPassword", f"{_IDT}:sendOobCode"
REFRESH = "https://securetoken.googleapis.com/v1/token"
GENERIC_RESET_MESSAGE = ("Se existir uma conta com este e-mail, enviaremos um link para "
                         "redefinir a senha. Confira também o spam.")

_MESSAGES = {
    "EMAIL_EXISTS": "Este e-mail já está cadastrado. Tente entrar ou recuperar a senha.",
    "INVALID_LOGIN_CREDENTIALS": "E-mail ou senha incorretos.",
    "INVALID_PASSWORD": "E-mail ou senha incorretos.",
    "EMAIL_NOT_FOUND": "E-mail ou senha incorretos.",
    "INVALID_EMAIL": "Informe um e-mail válido.",
    "USER_DISABLED": "Esta conta está desativada.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Muitas tentativas. Aguarde alguns minutos e tente de novo.",
    "WEAK_PASSWORD": f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres.",
    "OPERATION_NOT_ALLOWED": "Login por e-mail/senha não está ativado no Firebase (veja o README).",
    "CONFIGURATION_NOT_FOUND": (
        "O Firebase Authentication ainda não foi inicializado neste projeto. "
        "No Firebase Console, abra Authentication e clique em Get started. "
        "Depois, em Sign-in method, ative E-mail/senha. Confira também se "
        "[firebase].project_id e [firebase_web].api_key são do mesmo projeto."
    ),
    "API": "Chave de API do Firebase inválida. Confira [firebase_web] no secrets.toml.",
}


class AuthError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


class TokenError(Exception):
    """ID token inválido ou expirado."""

    def __init__(self, reason: str = ""):
        super().__init__(reason)
        self.reason = reason


def _token_hint(reason: str) -> str:
    low = reason.lower()
    if "aud" in low or "project" in low or "iss" in low:
        return ("O projeto da conta de serviço ([firebase] project_id) é diferente do projeto da "
                "chave de API ([firebase_web] api_key). Use credenciais do MESMO projeto Firebase.")
    if "too early" in low or "too late" in low or "clock" in low:
        return "O relógio deste computador está desajustado. Sincronize a data e a hora e tente de novo."
    if "certificate" in low or "connection" in low or "fetch" in low or "timeout" in low:
        return "Falha ao baixar os certificados do Google. Verifique a internet/proxy e tente de novo."
    return f"Não foi possível validar sua sessão ({reason[:140]})."


@dataclass
class AuthSession:
    uid: str
    email: str
    name: str
    id_token: str
    refresh_token: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AuthSession":
        return cls(**{f.name: data[f.name] for f in fields(cls)})


# ---------- infraestrutura ----------
def _friendly(code: str) -> str:
    return _MESSAGES.get(code, "Não foi possível concluir a operação. Tente novamente.")


def _api_key() -> str:
    try:
        key = st.secrets["firebase_web"]["api_key"]
    except Exception as exc:
        raise AuthError("Chave de API ausente. Configure [firebase_web] api_key no secrets.toml.") from exc
    if not key:
        raise AuthError("Chave de API ausente. Configure [firebase_web] api_key no secrets.toml.")
    return key


def _post(endpoint: str, payload: dict, *, form: bool = False) -> dict:
    kwargs = {"data": payload} if form else {"json": payload}
    try:
        resp = requests.post(f"{endpoint}?key={_api_key()}", timeout=15, **kwargs)
    except requests.RequestException as exc:
        raise AuthError("Falha de conexão com o Firebase. Tente novamente.") from exc
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 400:
        code = str(body.get("error", {}).get("message", "UNKNOWN")).split(" ")[0]
        raise AuthError(_friendly(code), code=code)
    return body


def _verify_id_token(token: str) -> dict:
    from firebase_admin import auth as fb_auth
    init_app()
    try:
        return fb_auth.verify_id_token(token, clock_skew_seconds=60)
    except Exception as exc:
        raise TokenError(f"{type(exc).__name__}: {exc}") from exc


def _admin_delete_user(uid: str) -> None:
    from firebase_admin import auth as fb_auth
    init_app()
    fb_auth.delete_user(uid)


def _safe_verify(token: str) -> dict | None:
    try:
        return _verify_id_token(token)
    except TokenError:
        return None


# ---------- validação ----------
def validate_signup(name: str, email: str, password: str, confirm: str) -> tuple[str, str]:
    name, email = (name or "").strip(), (email or "").strip().lower()
    if not (name and email and password and confirm):
        raise AuthError("Preencha todos os campos.")
    if len(name) < 2 or len(name) > 80:
        raise AuthError("Informe seu nome completo.")
    if not EMAIL_RE.match(email):
        raise AuthError("Informe um e-mail válido.")
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres.")
    if password != confirm:
        raise AuthError("A confirmação de senha não confere.")
    return name, email


# ---------- perfil (Firestore: users/{uid}) ----------
def create_profile(uid: str, name: str, email: str, *, db=None) -> None:
    resolve_db(db).collection("users").document(uid).set({
        "uid": uid, "name": name, "email": email,
        "created_at": SERVER_TIMESTAMP, "updated_at": SERVER_TIMESTAMP,
    })


def get_profile(uid: str, *, db=None) -> dict | None:
    snap = resolve_db(db).collection("users").document(uid).get()
    return snap.to_dict() if snap.exists else None


# ---------- fluxos ----------
def _build_session(body: dict, email: str, name: str) -> AuthSession:
    try:
        claims = _verify_id_token(body["idToken"])
    except TokenError as exc:
        raise AuthError(_token_hint(exc.reason), code="TOKEN") from exc
    return AuthSession(claims["uid"], email, name, body["idToken"], body["refreshToken"])


def sign_up(name: str, email: str, password: str, confirm: str, *, db=None) -> AuthSession:
    name, email = validate_signup(name, email, password, confirm)
    body = _post(SIGN_UP, {"email": email, "password": password, "returnSecureToken": True})
    uid = body["localId"]
    try:
        create_profile(uid, name, email, db=db)
    except Exception as exc:  # evita conta sem perfil: desfaz a criação no Authentication
        try:
            _admin_delete_user(uid)
        except Exception:
            pass
        raise AuthError("Não foi possível concluir o cadastro. Tente novamente.") from exc
    return _build_session(body, email, name)


def sign_in(email: str, password: str, *, db=None) -> AuthSession:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email) or not password:
        raise AuthError("Informe e-mail e senha.")
    body = _post(SIGN_IN, {"email": email, "password": password, "returnSecureToken": True})
    session = _build_session(body, email, email.split("@")[0])
    try:
        profile = get_profile(session.uid, db=db)
        if profile and profile.get("name"):
            session.name = profile["name"]
    except Exception:
        pass  # perfil indisponível não impede o login
    return session


def send_password_reset(email: str) -> str:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("Informe um e-mail válido.")
    try:
        _post(SEND_OOB, {"requestType": "PASSWORD_RESET", "email": email})
    except AuthError as exc:
        if exc.code != "EMAIL_NOT_FOUND":  # não revela se o e-mail existe
            raise
    return GENERIC_RESET_MESSAGE


def _refresh(session: AuthSession) -> None:
    body = _post(REFRESH, {"grant_type": "refresh_token", "refresh_token": session.refresh_token}, form=True)
    session.id_token = body["id_token"]
    session.refresh_token = body.get("refresh_token", session.refresh_token)


def authenticate(state) -> AuthSession | None:
    """Valida a sessão no servidor a cada rerun (renova o token se expirou).

    Retorna None (e limpa a sessão) se não houver identidade comprovada.
    """
    raw = state.get(SESSION_KEY)
    if not raw:
        return None
    try:
        session = AuthSession.from_dict(raw)
        claims = _safe_verify(session.id_token)
        if claims is None:
            _refresh(session)
            claims = _safe_verify(session.id_token)
    except (KeyError, TypeError, AuthError):
        claims = None
    if not claims or not claims.get("uid"):
        state.pop(SESSION_KEY, None)
        return None
    session.uid = claims["uid"]  # UID confiável: vem do token verificado
    state[SESSION_KEY] = session.to_dict()
    return session


def logout(state) -> None:
    """Encerra a sessão e apaga todo o estado (tokens, formulário, filtros)."""
    state.clear()