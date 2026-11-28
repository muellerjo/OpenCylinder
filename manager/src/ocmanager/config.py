"""Settings from environment variables (prefix OCM_) or a .env file in the data dir."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OCM_", env_file=".env", extra="ignore")

    # "local": single PC, binds to 127.0.0.1, may drive a Proxmark3 attached to it.
    # "server": multi-user deployment behind a TLS reverse proxy; secure cookies.
    mode: str = Field("local", pattern="^(local|server)$")
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"   # manager/data
    database_url: str | None = None            # default: sqlite in data_dir
    # Key-encryption key for site secrets (32 bytes hex). Default: data_dir/master.key
    master_key: str | None = None
    session_secret: str | None = None          # default: data_dir/session.key
    session_max_age: int = 8 * 3600
    modules: str = "*"                          # comma list of module names, "*" = all
    pm3_path: str | None = None                 # Proxmark3 client: enables the local encoder
    pm3_port: str | None = None
    allow_dev_keys: bool = True                 # allow importing the public bench test keys

    @property
    def secure_cookies(self) -> bool:
        return self.mode == "server"

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'ocmanager.db').resolve()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
