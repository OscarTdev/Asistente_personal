import uuid
from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password():
    """Test password hashing."""
    hashed = hash_password("Admin1234!")
    assert hashed != "Admin1234!"
    assert verify_password("Admin1234!", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_create_and_decode_access_token():
    """Test JWT token creation and decoding."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    role = "admin"

    token = create_access_token(user_id, tenant_id, role)
    assert isinstance(token, str)
    assert len(token) > 0

    decoded = decode_access_token(token)
    assert decoded["sub"] == str(user_id)
    assert decoded["tenant_id"] == str(tenant_id)
    assert decoded["role"] == role
    assert "exp" in decoded


def test_access_token_expiration():
    """Test that expired tokens raise an exception."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    role = "admin"

    # Create an expired token
    token = create_access_token(user_id, tenant_id, role, expires_delta=timedelta(seconds=-1))

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)