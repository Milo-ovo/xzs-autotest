from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """运行环境配置，优先读取项目根目录 .env 和系统环境变量。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    base_url: str = Field("http://localhost:8000", validation_alias="BASE_URL")
    admin_user: str = Field("admin", validation_alias="ADMIN_USER")
    admin_password: str = Field("123456", validation_alias="ADMIN_PASSWORD")
    student_user: str = Field("student", validation_alias="STUDENT_USER")
    student_password: str = Field("123456", validation_alias="STUDENT_PASSWORD")
    request_timeout: float = Field(15.0, validation_alias="REQUEST_TIMEOUT")
    run_integration: bool = Field(False, validation_alias="RUN_INTEGRATION")
    time_paper_start: str = Field("2026-01-01 00:00:00", validation_alias="TIME_PAPER_START")
    time_paper_end: str = Field("2099-12-31 23:59:59", validation_alias="TIME_PAPER_END")

    db_host: str = Field("localhost", validation_alias="DB_HOST")
    db_port: int = Field(3306, validation_alias="DB_PORT")
    db_user: str = Field("root", validation_alias="DB_USER")
    db_password: str = Field("123456", validation_alias="DB_PASSWORD")
    db_name: str = Field("xzs", validation_alias="DB_NAME")

    # 会话末数据对账：true 时残留即 fail，false 时只 warning（默认，不破坏本地绿色）
    fail_on_residue: bool = Field(False, validation_alias="FAIL_ON_RESIDUE")

    @property
    def api_base_url(self) -> str:
        return self.base_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

