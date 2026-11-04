"""Botão circular + (botão real do Streamlit, fixado e centralizado via CSS)."""
import streamlit as st


def render_fab(on_click) -> None:
    with st.container(key="fab"):
        st.button("+", key="fab_btn", on_click=on_click, help="Nova movimentação")
