from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    COMMUNITY_TOKEN: str
    ADMIN_TOKEN: str
    SERVER_URI: str
    GROUP_ID: int

    class Config:
        env_file = '../.env'
        env_file_encoding = 'utf-8'
