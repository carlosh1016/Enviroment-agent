from decouple import Csv, config


class Settings:
    """Configuracion centralizada de la aplicacion, leida desde variables de entorno."""

    ENVIRONMENT: str = config("ENVIRONMENT", default="development")

    DATABASE_URL: str = config(
        "DATABASE_URL",
        default="postgresql+asyncpg://ecolex_user:ecolex_password@postgres:5432/ecolex",
    )

    SECRET_KEY: str = config("SECRET_KEY")
    ALGORITHM: str = config("JWT_ALGORITHM", default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = config("ACCESS_TOKEN_EXPIRE_MINUTES", default=30, cast=int)
    REFRESH_TOKEN_EXPIRE_DAYS: int = config("REFRESH_TOKEN_EXPIRE_DAYS", default=7, cast=int)

    ALLOWED_ORIGINS: list = config(
        "ALLOWED_ORIGINS", default="http://localhost:3000", cast=Csv()
    )

    REFRESH_COOKIE_NAME: str = config("REFRESH_COOKIE_NAME", default="refresh_token")
    COOKIE_SECURE: bool = config("COOKIE_SECURE", default=True, cast=bool)

    RATE_LIMIT_LOGIN: str = config("RATE_LIMIT_LOGIN", default="5/minute")

    GOOGLE_API_KEY: str = config("GOOGLE_API_KEY")
    OPENROUTER_API_KEY: str = config("OPENROUTER_API_KEY", default="")


settings = Settings()
