"""Tests del parser de intenciones tolerante a modelos de razonamiento.

Nemotron-3 puede anteponer su cadena de pensamiento o citar ejemplos
JSON antes del JSON final: el parser debe tomar el bloque válido
correcto, no el primero que aparezca.
"""

import pytest

from app.services.assistant import _parse_intent


def test_parse_intent_clean_json():
    intent = _parse_intent('{"intention": "chat"}')
    assert intent.intention == "chat"


def test_parse_intent_json_with_surrounding_text():
    raw = "Claro, aquí va:\n```json\n{\"intention\": \"note\"}\n```\nListo."
    intent = _parse_intent(raw)
    assert intent.intention == "note"


def test_parse_intent_reasoning_chain_then_final_json():
    """El razonamiento cita un ejemplo; el JSON FINAL es la respuesta."""
    raw = (
        "The user said 'hola'. Let me think about this. "
        "This is a greeting, not an action. "
        'For example {"intention": "chat"} would be wrong here. '
        "The user is greeting me. "
        'Final answer: {"intention": "send_message", '
        '"contact_name": "Juliana", '
        '"message_text": "Buenos días Juliana"}'
    )
    intent = _parse_intent(raw)
    assert intent.intention == "send_message"
    assert intent.contact_name == "Juliana"


def test_parse_intent_nested_json():
    raw = '{"intention": "expense", "description": "cable {especial} 12m"}'
    intent = _parse_intent(raw)
    assert intent.intention == "expense"
    assert intent.description == "cable {especial} 12m"


def test_parse_intent_only_reasoning_raises():
    with pytest.raises(ValueError):
        _parse_intent(
            "The user wants to do two things: create a reminder and "
            "search the internet. I should analyze this further."
        )


def test_parse_intent_multiple_json_blocks_takes_valid_last():
    """Varios bloques: gana el ÚLTIMO que valide como AssistantIntent."""
    raw = (
        '{"intention": "unknown_bogus"} '  # no es un intention válido
        '{"intention": "web_search", "message_text": "precio cobre"}'
    )
    intent = _parse_intent(raw)
    assert intent.intention == "web_search"
    assert intent.message_text == "precio cobre"