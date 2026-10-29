"""Sincronización y verificación de hora via NTP."""

import logging
import socket
import struct
import time
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Servidores NTP públicos confiables
NTP_SERVERS = [
    "pool.ntp.org",
    "time.google.com",
    "time.cloudflare.com",
    "time.windows.com",
]

# Formato del paquete NTP
NTP_PACKET_FORMAT = "!12I"
NTP_DELTA = 2208988800  # Diferencia entre epoch NTP (1900) y Unix (1970)
NTP_PORT = 123
NTP_TIMEOUT = 5  # segundos


def _ntp_request(server: str) -> float | None:
    """
    Realiza una petición NTP simple y retorna el offset en segundos.
    Retorna None si falla.
    """
    try:
        # Crear socket UDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(NTP_TIMEOUT)

        # Construir paquete NTP (modo cliente, versión 3)
        packet = bytearray(48)
        packet[0] = 0x1B  # LI=0, VN=3, Mode=3 (cliente)

        # Enviar
        sock.sendto(packet, (server, NTP_PORT))

        # Recibir respuesta
        data, _ = sock.recvfrom(1024)
        sock.close()

        if len(data) < 48:
            return None

        # Desempaquetar respuesta
        unpacked = struct.unpack(NTP_PACKET_FORMAT, data[:48])

        # Transmit timestamp (segundos desde 1900)
        transmit_timestamp = unpacked[10] + unpacked[11] / 2**32

        # Convertir a epoch Unix
        ntp_time = transmit_timestamp - NTP_DELTA

        # Calcular offset (diferencia entre hora NTP y hora local)
        local_time = time.time()
        offset = ntp_time - local_time

        return offset

    except Exception as e:
        logger.debug("NTP request to %s failed: %s", server, e)
        return None


def check_ntp_time() -> tuple[bool, float | None, str | None]:
    """
    Verifica la hora del sistema contra servidores NTP.
    
    Returns:
        (is_ok, offset_seconds, server_used)
        - is_ok: True si el offset es < 5 segundos
        - offset_seconds: diferencia (positivo = sistema atrasado)
        - server_used: servidor NTP que respondió
    """
    for server in NTP_SERVERS:
        offset = _ntp_request(server)
        if offset is not None:
            is_ok = abs(offset) < 5.0  # Tolerancia de 5 segundos
            return is_ok, offset, server

    return False, None, None


def get_ntp_time() -> datetime | None:
    """
    Obtiene la hora actual desde un servidor NTP.
    Retorna datetime en UTC o None si falla.
    """
    for server in NTP_SERVERS:
        offset = _ntp_request(server)
        if offset is not None:
            # Ajustar la hora local con el offset
            corrected_time = time.time() + offset
            return datetime.fromtimestamp(corrected_time, tz=UTC)

    return None


async def sync_system_time_if_needed() -> bool:
    """
    Verifica la hora y loguea warning si está desincronizada.
    En contenedores, la sincronización real debe hacerse en el host.
    """
    is_ok, offset, server = check_ntp_time()

    if offset is not None:
        if is_ok:
            logger.info("NTP check OK: offset=%.3fs (server: %s)", offset, server)
        else:
            logger.warning(
                "RELOJ DESINCRONIZADO: offset=%.3fs (server: %s). "
                "Los recordatorios y tareas programadas pueden fallar. "
                "Configurar NTP en el host: 'timedatectl set-ntp true' o instalar chrony/ntpd.",
                offset, server
            )
        return is_ok
    else:
        logger.warning(
            "No se pudo contactar servidores NTP. "
            "Verificar conectividad de red y firewall (UDP 123)."
        )
        return False