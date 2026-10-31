import jwt
import pytest

from app.core.security import create_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("correct horse battery")
    assert verify_password("correct horse battery", h)
    assert not verify_password("wrong", h)


def test_verify_without_user_is_false():
    assert not verify_password("dummy-password-for-timing", None)
    assert not verify_password("anything", "not-a-hash")


def test_token_type_is_enforced():
    refresh = create_token(1, "ADMIN", "refresh")
    assert decode_token(refresh, "refresh")["sub"] == "1"
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(refresh, "access")


def test_tampered_token_rejected():
    token = create_token(1, "VIEWER", "access")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token[:-2] + ("AA" if token[-2:] != "AA" else "BB"), "access")
