"""Finance Flow — streamlit run app.py"""
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Finance Flow", page_icon="💜", layout="wide",
                   initial_sidebar_state="collapsed")

from database.firebase import FirebaseConfigError, get_db  # noqa: E402
from services.auth import authenticate  # noqa: E402
from views.auth import render_auth  # noqa: E402
from views.dashboard import render_dashboard  # noqa: E402
from views.transaction_form import render_form  # noqa: E402


def load_css() -> None:
    css = (Path(__file__).parent / "styles" / "main.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def main() -> None:
    load_css()
    try:
        get_db()
    except FirebaseConfigError as exc:
        st.error(f"Firebase não configurado: {exc}")
        st.info("Siga o passo a passo do README.md (seção de configuração do Firebase) e reinicie o app.")
        st.stop()

    user = authenticate(st.session_state)  # identidade verificada no servidor
    if user is None:
        render_auth()
        return
    if st.session_state.get("view") == "form":
        render_form(user)
    else:
        render_dashboard(user)


main()
