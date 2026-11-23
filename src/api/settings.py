"""Cấu hình API (biến môi trường). Không có khóa bí mật: API gọi Supabase bằng JWT người dùng."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""  # https://<ref>.supabase.co
    supabase_publishable_key: str = ""  # sb_publishable_... (công khai, header "apikey")
    cors_origins: str = "http://localhost:3000"  # nhiều domain cách nhau dấu phẩy
    parse_timeout_s: float = 10.0  # quá thì kill tiến trình đọc, trả 504
    parse_workers: int = 1  # số tiến trình đọc CV nạp sẵn; 0 = chạy ngay trong request (test)
    rate_limit_per_minute: int = 10  # mỗi người dùng
    max_cv_bytes: int = 5 * 1024 * 1024
    timezone: str = "Asia/Ho_Chi_Minh"
    # API Top N (S4-D04): kết nối CHỈ ĐỌC role matcher_ro (migration 0012). Trống = tắt /match/jobs.
    matcher_database_url: str = ""
    match_refresh_seconds: int = 3600  # dựng lại kho tin trong RAM
    match_rate_limit_per_minute: int = 20
    # S4-T04: role api_metrics_writer (migration 0019). Trống = không ghi số đo độ trễ.
    metrics_database_url: str = ""

    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def jwt_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
