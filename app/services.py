import os

from mor_api_services import MORCoreService as BasisMORCoreService


class MORCoreService(BasisMORCoreService):
    def __init__(self, *args, **kwargs):
        kwargs.update(
            {
                "basis_url": os.getenv("MOR_CORE_URL", "http://core.mor.local:8002"),
                "gebruikersnaam": os.getenv("MOR_CORE_USER", "automatr"),
                "wachtwoord": os.getenv("MOR_CORE_PASSWORD", "insecure"),
                "token_timeout": 0,
            }
        )
        super().__init__(*args, **kwargs)
