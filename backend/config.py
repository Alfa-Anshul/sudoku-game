from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MCP Backend"
    environment: str = "dev"
    secret_key: str = "replace-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    database_url: str = "sqlite:///./app.db"
    redis_url: str = ""

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"

    mcp_service_url: str = "http://localhost:8000"
    mcp_api_key: str = "change-this-mcp-key"
    mcp_auth_mode: str = "none"
    public_base_url: str = "https://alfamcp.grgonline.com"
    local_saver_url: str = ""
    local_saver_api_key: str = ""
    github_token: str = ""
    deploy_ssh_host: str = ""
    deploy_ssh_port: int = 22
    deploy_ssh_user: str = "ubuntu"
    deploy_ssh_key_path: str = ""
    deploy_ssh_private_key: str = ""
    deploy_public_host: str = ""
    deploy_public_scheme: str = "http"
    deploy_base_dir: str = "/opt/mcp-deployments"
    deploy_port_start: int = 8600
    deploy_port_end: int = 8699
    deploy_docker_command: str = "docker"
    deploy_certbot_email: str = ""
    hostinger_api_token: str = ""
    hostinger_api_base_url: str = "https://developers.hostinger.com"

    oauth_introspection_url: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
