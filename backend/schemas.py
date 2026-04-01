from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    service: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    response: str


class ToolExecuteRequest(BaseModel):
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolExecuteResponse(BaseModel):
    ok: bool
    result: dict[str, Any]


class DeployInDockerRequest(BaseModel):
    github_repo_url: str
    branch: str = "main"
    app_name: str | None = None
    fastapi_module: str | None = None
    public_host: str | None = None
    deploy_public_host: str | None = None
    deploy_ssh_host: str | None = None
    deploy_ssh_user: str | None = None
    deploy_ssh_port: int | None = None
    deploy_ssh_key_path: str | None = None
    deploy_ssh_private_key: str | None = None
    deploy_docker_command: str | None = None


class MapDomainRequest(BaseModel):
    domain: str
    container_name: str | None = None
    port: int | None = None
    docs_path: str = "/docs"
    deploy_ssh_host: str | None = None
    deploy_ssh_user: str | None = None
    deploy_ssh_port: int | None = None
    deploy_ssh_key_path: str | None = None
    deploy_ssh_private_key: str | None = None
    deploy_docker_command: str | None = None
    certbot_email: str | None = None
    hostinger_api_token: str | None = None
    hostinger_zone_domain: str | None = None
    dns_target_ip: str | None = None
    include_www_alias: bool = True
    enable_https: bool = True


class MemoryCreateRequest(BaseModel):
    key: str
    value: str


class MemoryOut(BaseModel):
    id: int
    key: str
    value: str
    created_at: datetime

    class Config:
        from_attributes = True


class NoteCreateRequest(BaseModel):
    user_id: int
    title: str
    content: str


class OAuthExchangeRequest(BaseModel):
    provider_token: str
