"""Argon2PasswordHasher: саме argon2id, параметри у самому хеші."""

from anyio.from_thread import BlockingPortal

from infrastructure.security.passwords import Argon2PasswordHasher


def test_hash_is_argon2id_with_embedded_parameters(portal: BlockingPortal) -> None:
    stored = portal.call(Argon2PasswordHasher().hash, "correct horse battery")
    assert stored.value.startswith("$argon2id$v=19$m=")
    assert ",t=" in stored.value
    assert ",p=" in stored.value
