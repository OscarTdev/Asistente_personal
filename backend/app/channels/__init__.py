from .base import Channel
from .evolution import EvolutionChannel

_CHANNELS = {
    "evolution": EvolutionChannel,
}


def get_channel(name: str) -> Channel:
    """Devuelve la instancia del canal por nombre."""
    try:
        return _CHANNELS[name]()
    except KeyError:
        raise ValueError(f"Canal desconocido: {name}") from None