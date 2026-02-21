import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-key")
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/agent_system")
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    SQLALCHEMY_ECHO: bool = os.environ.get("SQLALCHEMY_ECHO", "false").lower() == "true"

    # Crawl rate limits (requests per second)
    PYPI_CRAWL_RATE_LIMIT: int = int(os.environ.get("PYPI_CRAWL_RATE_LIMIT", "50"))
    NPM_CRAWL_RATE_LIMIT: int = int(os.environ.get("NPM_CRAWL_RATE_LIMIT", "50"))

    # OSV API
    OSV_API_URL: str = os.environ.get("OSV_API_URL", "https://api.osv.dev/v1")


class TestConfig(Config):
    TESTING: bool = True
    DATABASE_URL: str = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
