"""App config: single-user local defaults, PERFI_ prefix."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "perfi"
    database_url: str = "sqlite:///./data/perfi.db"
    plaid_enabled: bool = False
    simplefin_enabled: bool = False

    model_config = {"env_prefix": "PERFI_"}


settings = Settings()
