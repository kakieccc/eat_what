import asyncio

from pwdlib import PasswordHash


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._passwords = PasswordHash.recommended()
        self.dummy_hash = self._passwords.hash("not-a-real-account-password")

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._passwords.hash, password)

    async def verify(self, password: str, encoded: str) -> bool:
        return await asyncio.to_thread(self._passwords.verify, password, encoded)
