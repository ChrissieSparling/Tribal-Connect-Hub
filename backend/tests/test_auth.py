import os, sys

HERE = os.path.dirname(__file__)
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.common.auth import hash_password, safe_verify_password


def test_hash_and_verify_password():
    hashed = hash_password("s3cret")
    assert safe_verify_password("s3cret", hashed)
    assert not safe_verify_password("wrong", hashed)