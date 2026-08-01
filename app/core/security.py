import hashlib
from dataclasses import dataclass

CHAT_COMPLETIONS_SCOPE = "chat:completions"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Principal:
    label: str
    scopes: frozenset[str]

    @property
    def is_anonymous(self) -> bool:
        return self.label == "anonymous"

    def may(self, scope: str) -> bool:
        return not self.scopes or scope in self.scopes


ANONYMOUS = Principal(label="anonymous", scopes=frozenset())
