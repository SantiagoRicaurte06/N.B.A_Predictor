"""
Control de acceso del dashboard.

Login con OpenID Connect (Google) mediante `st.login` y una lista de correos
autorizados. Se configura en `.streamlit/secrets.toml` (ver
`.streamlit/secrets.toml.example`). Si falta la configuración, el dashboard
no arranca: solo se puede omitir el login en local con NBA_SIN_LOGIN=1.
"""

from __future__ import annotations

import os

import streamlit as st


def correo_autorizado(correo: str | None, autorizados, verificado: bool | None = True) -> bool:
    """True si el correo está en la lista y el proveedor lo marca como verificado."""
    if not correo or verificado is False:
        return False
    lista = {c.strip().lower() for c in autorizados or [] if c and c.strip()}
    return correo.strip().lower() in lista


def _secretos() -> dict:
    try:
        return {"auth": dict(st.secrets["auth"]), "acceso": dict(st.secrets.get("acceso", {}))}
    except (KeyError, FileNotFoundError):
        return {}


def exigir_login() -> None:
    """Detiene la página hasta que un correo autorizado inicie sesión."""
    if os.environ.get("NBA_SIN_LOGIN") == "1":
        st.sidebar.warning("Login desactivado (NBA_SIN_LOGIN=1). Solo para uso local.",
                           icon=":material/lock_open:")
        return

    secretos = _secretos()
    autorizados = secretos.get("acceso", {}).get("correos", [])
    if not secretos or not autorizados:
        st.error("Falta configurar el login: `[auth]` y `[acceso] correos` en "
                 "`.streamlit/secrets.toml`. Ver docs/DESPLIEGUE.md.", icon=":material/lock:")
        st.stop()

    if not st.user.get("is_logged_in"):
        _, centro, _ = st.columns([1, 2, 1])
        with centro:
            st.title("NBA Predictor")
            st.caption("Acceso privado. Inicia sesión con una cuenta autorizada.")
            st.button("Iniciar sesión con Google", icon=":material/login:",
                      on_click=st.login, width="stretch")
        st.stop()

    if not correo_autorizado(st.user.get("email"), autorizados, st.user.get("email_verified")):
        st.error(f"La cuenta {st.user.get('email', '')} no tiene acceso.", icon=":material/block:")
        st.button("Cerrar sesión", icon=":material/logout:", on_click=st.logout)
        st.stop()
