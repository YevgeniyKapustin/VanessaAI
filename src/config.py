from pydantic import BaseSettings


class Settings(BaseSettings):
    """Конфиг Ванессы."""
    COMMUNITY_TOKEN: str

    class Config:
        env_file = '../.env'
        env_file_encoding = 'utf-8'


settings = Settings()
