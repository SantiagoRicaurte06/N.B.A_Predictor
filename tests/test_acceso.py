"""Acceso: solo entran correos de la lista, verificados y sin importar mayúsculas."""

from app.acceso import correo_autorizado

LISTA = ["Santiago@Example.com", " otro@example.com "]


def test_correo_en_la_lista_entra():
    assert correo_autorizado("santiago@example.com", LISTA)
    assert correo_autorizado("OTRO@example.com", LISTA)


def test_correo_fuera_de_la_lista_no_entra():
    assert not correo_autorizado("intruso@example.com", LISTA)


def test_sin_correo_o_sin_lista_no_entra():
    assert not correo_autorizado(None, LISTA)
    assert not correo_autorizado("", LISTA)
    assert not correo_autorizado("santiago@example.com", [])


def test_correo_no_verificado_no_entra():
    assert not correo_autorizado("santiago@example.com", LISTA, verificado=False)
    assert correo_autorizado("santiago@example.com", LISTA, verificado=None)
