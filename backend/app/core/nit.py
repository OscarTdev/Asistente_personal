"""Validación del NIT colombiano (dígito de verificación de la DIAN).

Solo se pide para cuentas de negocio o empresa; las personas naturales no
declaran documento en el registro.
"""

import re

# Pesos oficiales de la DIAN, aplicados de derecha a izquierda (ciclando)
_NIT_WEIGHTS = (3, 7, 9, 11, 13, 17, 19, 23)

# Formato aceptado: 900.123.456-7 (puntos y espacios opcionales) o 900123456-7
_NIT_RE = re.compile(r"^\d{6,14}-\d$")


def compute_nit_check_digit(base_digits: str) -> int:
    """Calcula el dígito de verificación de un NIT sin DV (algoritmo DIAN)."""
    total = 0
    for position, digit in enumerate(reversed(base_digits)):
        total += int(digit) * _NIT_WEIGHTS[position % len(_NIT_WEIGHTS)]
    remainder = total % 11
    if remainder > 1:
        return 11 - remainder
    return remainder


def validate_nit(value: str) -> bool:
    """¿Es un NIT bien formado y con dígito de verificación correcto?"""
    if not value:
        return False
    clean = value.replace(".", "").replace(" ", "").strip()
    if not _NIT_RE.match(clean):
        return False
    base, _, check = clean.rpartition("-")
    if not base.isdigit():
        return False
    return compute_nit_check_digit(base) == int(check)


def clean_nit(value: str) -> str:
    """Normaliza el NIT a su forma canónica: dígitos + guion + DV."""
    return value.replace(".", "").replace(" ", "").strip()
