"""Tests del validador de NIT (dígito de verificación DIAN)."""

from app.core.nit import clean_nit, compute_nit_check_digit, validate_nit


def test_check_digit_computation():
    """El algoritmo DIAN: pesos 3,7,9,11,13,17,19,23 de derecha a izquierda."""
    # Base 900123456: 6*3 + 5*7 + 4*9 + 3*11 + 2*13 + 1*17 + 0*19 + 0*23 + 9*3
    # = 18+35+36+33+26+17+0+0+27 = 192; 192 % 11 = 5 → DV = 11 - 5 = 6
    assert compute_nit_check_digit("900123456") == 6


def test_validate_nit_formats():
    """Acepta puntos y espacios; exige el guion con el dígito."""
    assert validate_nit("900.123.456-6")
    assert validate_nit("900123456-6")
    assert validate_nit(" 900.123.456 - 6 ")
    assert not validate_nit("900123456")       # sin dígito
    assert not validate_nit("900.123.456-")    # dígito vacío
    assert not validate_nit("no-un-nit-7")     # no numérico
    assert not validate_nit("")               # vacío


def test_validate_nit_wrong_check_digit():
    """El dígito de verificación debe cuadrar."""
    assert validate_nit("900123456-6")
    assert not validate_nit("900123456-7")
    assert not validate_nit("900123456-0")


def test_clean_nit():
    assert clean_nit(" 900.123.456-6 ") == "900123456-6"
