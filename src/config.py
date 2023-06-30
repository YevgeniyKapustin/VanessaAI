from pydantic import BaseSettings


class Settings(BaseSettings):
    COMMUNITY_TOKEN: str
    SERVER_URI: str


settings = Settings()
