from pydantic import BaseSettings


class Settings(BaseSettings):
    """Конфиг приложения."""
    COMMUNITY_TOKEN: str

    class Config:
        env_file = '../.env'
        env_file_encoding = 'utf-8'
