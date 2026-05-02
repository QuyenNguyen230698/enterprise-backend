from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Gateway City - Meeting API"

    # --- CẤU HÌNH POSTGRESQL ---
    POSTGRES_USER: str = "admin"
    POSTGRES_PASSWORD: str = "secretpassword"
    # Khi chạy local không có Docker thì là localhost.
    # Khi chạy trong Docker thì đổi thành tên service (VD: "postgres")
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "meeting_db"

    # --- CẤU HÌNH ZOOM SERVER-TO-SERVER OAUTH ---
    ZOOM_ACCOUNT_ID: str = ""
    ZOOM_CLIENT_ID: str = ""
    ZOOM_CLIENT_SECRET: str = ""

    BACKEND_URL: str = "http://localhost:8000"

    # AES encryption key for SMTP credentials (Fernet 32-byte URL-safe base64)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = ""



    # Hàm tự động build chuỗi kết nối DB bất đồng bộ (asyncpg)
    @property
    def async_database_url(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        case_sensitive = True
        env_file = None


settings = Settings()
