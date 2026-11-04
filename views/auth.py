"""Telas de login, cadastro e recuperação de senha."""
import streamlit as st

from services.auth import SESSION_KEY, AuthError, send_password_reset, sign_in, sign_up


def _go(mode: str):
    st.session_state["auth_mode"] = mode


def _login() -> None:
    st.markdown("<h2 class='ff-title'>Bem-vindo de volta</h2><p class='ff-sub'>Entre para acompanhar seu dinheiro.</p>",
                unsafe_allow_html=True)
    with st.form("login_form", border=False):
        email = st.text_input("E-mail", key="login_email")
        password = st.text_input("Senha", type="password", key="login_password")
        submitted = st.form_submit_button("Entrar", type="primary", use_container_width=True)
    if submitted:
        try:
            st.session_state[SESSION_KEY] = sign_in(email, password).to_dict()
        except AuthError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    st.button("Criar minha conta", key="go_signup", use_container_width=True, on_click=_go, args=("signup",))
    st.button("Esqueci minha senha", key="go_reset", use_container_width=True, on_click=_go, args=("reset",))


def _signup() -> None:
    st.markdown("<h2 class='ff-title'>Criar minha conta</h2><p class='ff-sub'>Leva menos de um minuto.</p>",
                unsafe_allow_html=True)
    with st.form("signup_form", border=False):
        name = st.text_input("Nome completo", key="su_name")
        email = st.text_input("E-mail", key="su_email")
        password = st.text_input("Senha", type="password", key="su_password")
        confirm = st.text_input("Confirmar senha", type="password", key="su_confirm")
        submitted = st.form_submit_button("Criar conta", type="primary", use_container_width=True)
    if submitted:
        try:
            st.session_state[SESSION_KEY] = sign_up(name, email, password, confirm).to_dict()
        except AuthError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    st.button("Já tenho conta", key="back_login", use_container_width=True, on_click=_go, args=("login",))


def _reset() -> None:
    st.markdown("<h2 class='ff-title'>Recuperar senha</h2><p class='ff-sub'>Enviaremos um link para o seu e-mail.</p>",
                unsafe_allow_html=True)
    with st.form("reset_form", border=False):
        email = st.text_input("E-mail", key="rs_email")
        submitted = st.form_submit_button("Enviar link", type="primary", use_container_width=True)
    if submitted:
        try:
            st.success(send_password_reset(email))
        except AuthError as exc:
            st.error(str(exc))
    st.button("Voltar para o login", key="back_login2", use_container_width=True, on_click=_go, args=("login",))


def render_auth() -> None:
    mode = st.session_state.setdefault("auth_mode", "login")
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown('<div class="ff-brand ff-brand-lg"><span class="ff-logo">◆</span> Finance Flow</div>',
                    unsafe_allow_html=True)
        with st.container(key="auth_card"):
            {"login": _login, "signup": _signup, "reset": _reset}.get(mode, _login)()
