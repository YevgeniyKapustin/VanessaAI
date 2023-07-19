from pydantic import BaseSettings


class Settings(BaseSettings):
    COMMUNITY_TOKEN: str


settings = Settings()
