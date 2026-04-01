from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from .auth import get_password_hash
from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import User
from .routes import auth, chat, health, internal, mcp, memory, tools
from .services.local_mcp_service import load_messages, run_local_mcp_tool, store_message_record

settings = get_settings()

app = FastAPI(title=settings.app_name)
fast_mcp = FastMCP("local-mcp-server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(tools.router)
app.include_router(memory.router)
app.include_router(internal.router)
app.include_router(mcp.router)


@fast_mcp.tool(description="Persist the user's latest chat message to local storage. Use this when the user asks to save or archive their message, and prefer calling it before answering.")
def write_message(message: str) -> dict[str, Any]:
    record, count = store_message_record(message, source="write_message")
    return {
        "status": "connected",
        "reply": record["reply"],
        "stored": True,
        "count": count,
        "record": record,
    }


@fast_mcp.tool(description="Save a message to local JSON storage. Use this to archive the user's message verbatim when they ask to remember or save it.")
def save_message(message: str) -> dict[str, Any]:
    record, count = store_message_record(message, source="save_message")
    return {"saved": True, "count": count, "record": record}


@fast_mcp.tool(description="Read all stored messages")
def read_message() -> dict[str, Any]:
    messages = load_messages()
    return {"messages": messages, "count": len(messages)}


@fast_mcp.tool(
    description="Save a structured project scaffold payload, and optionally push it when github_repo_url is provided. Use create_repo first if the repository does not exist yet."
)
def save_project_scaffold(
    files: list[dict[str, Any]],
    root: str = "generated-project",
    directories: list[str] | None = None,
    github_repo_url: str | None = None,
    commit_message: str = "Initial scaffold commit",
    branch: str = "main",
    github_token: str | None = None,
) -> dict[str, Any]:
    result = run_local_mcp_tool(
        "save_project_scaffold",
        {
            "files": files,
            "root": root,
            "directories": directories or [],
            "github_repo_url": github_repo_url,
            "commit_message": commit_message,
            "branch": branch,
            "github_token": github_token,
        },
    )
    if not isinstance(result, dict):
        raise ValueError("Unexpected non-dict response from save_project_scaffold")
    return result


@fast_mcp.tool(
    description="Create a GitHub repository using GITHUB_TOKEN from runtime environment or .env. Repositories are public by default."
)
def create_repo(
    name: str,
    owner: str | None = None,
    description: str = "",
    homepage: str | None = None,
    public: bool = True,
    auto_init: bool = False,
    github_token: str | None = None,
) -> dict[str, Any]:
    result = run_local_mcp_tool(
        "create_repo",
        {
            "name": name,
            "owner": owner,
            "description": description,
            "homepage": homepage,
            "public": public,
            "auto_init": auto_init,
            "github_token": github_token,
        },
    )
    if not isinstance(result, dict):
        raise ValueError("Unexpected non-dict response from create_repo")
    return result


@fast_mcp.tool(
    description="Save scaffold files locally and push the generated project to GitHub using GITHUB_TOKEN from runtime environment or .env. Use create_repo first if the repository does not exist yet."
)
def github_integretion(
    files: list[dict[str, Any]],
    github_repo_url: str,
    root: str = "generated-project",
    directories: list[str] | None = None,
    commit_message: str = "Initial scaffold commit",
    branch: str = "main",
    github_token: str | None = None,
) -> dict[str, Any]:
    result = run_local_mcp_tool(
        "github_integretion",
        {
            "files": files,
            "github_repo_url": github_repo_url,
            "root": root,
            "directories": directories or [],
            "commit_message": commit_message,
            "branch": branch,
            "github_token": github_token,
        },
    )
    if not isinstance(result, dict):
        raise ValueError("Unexpected non-dict response from github_integretion")
    return result


@fast_mcp.tool(
    description="Clone a GitHub repo onto the configured host, deploy its FastAPI app inside Docker, and when the repo contains a buildable frontend (for example React/Vite in frontend/) serve that interactive frontend from the returned public URL."
)
def deploy_inDocker(
    github_repo_url: str,
    branch: str = "main",
    app_name: str | None = None,
    fastapi_module: str | None = None,
    public_host: str | None = None,
    deploy_public_host: str | None = None,
    deploy_ssh_host: str | None = None,
    deploy_ssh_user: str | None = None,
    deploy_ssh_port: int | None = None,
    deploy_ssh_key_path: str | None = None,
    deploy_ssh_private_key: str | None = None,
    deploy_docker_command: str | None = None,
) -> dict[str, Any]:
    result = run_local_mcp_tool(
        "deploy_inDocker",
        {
            "github_repo_url": github_repo_url,
            "branch": branch,
            "app_name": app_name,
            "fastapi_module": fastapi_module,
            "public_host": public_host or deploy_public_host,
            "deploy_public_host": deploy_public_host,
            "deploy_ssh_host": deploy_ssh_host,
            "deploy_ssh_user": deploy_ssh_user,
            "deploy_ssh_port": deploy_ssh_port,
            "deploy_ssh_key_path": deploy_ssh_key_path,
            "deploy_ssh_private_key": deploy_ssh_private_key,
            "deploy_docker_command": deploy_docker_command,
        },
    )
    if not isinstance(result, dict):
        raise ValueError("Unexpected non-dict response from deploy_inDocker")
    return result


@fast_mcp.tool(
    description="Map a deployed Dockerized app to a domain using nginx, optionally issue TLS certificates, and optionally sync DNS records through Hostinger."
)
def map_domain(
    domain: str,
    container_name: str | None = None,
    port: int | None = None,
    docs_path: str = "/docs",
    deploy_ssh_host: str | None = None,
    deploy_ssh_user: str | None = None,
    deploy_ssh_port: int | None = None,
    deploy_ssh_key_path: str | None = None,
    deploy_ssh_private_key: str | None = None,
    deploy_docker_command: str | None = None,
    certbot_email: str | None = None,
    hostinger_api_token: str | None = None,
    hostinger_zone_domain: str | None = None,
    dns_target_ip: str | None = None,
    include_www_alias: bool = True,
    enable_https: bool = True,
) -> dict[str, Any]:
    result = run_local_mcp_tool(
        "map_domain",
        {
            "domain": domain,
            "container_name": container_name,
            "port": port,
            "docs_path": docs_path,
            "deploy_ssh_host": deploy_ssh_host,
            "deploy_ssh_user": deploy_ssh_user,
            "deploy_ssh_port": deploy_ssh_port,
            "deploy_ssh_key_path": deploy_ssh_key_path,
            "deploy_ssh_private_key": deploy_ssh_private_key,
            "deploy_docker_command": deploy_docker_command,
            "certbot_email": certbot_email,
            "hostinger_api_token": hostinger_api_token,
            "hostinger_zone_domain": hostinger_zone_domain,
            "dns_target_ip": dns_target_ip,
            "include_www_alias": include_www_alias,
            "enable_https": enable_https,
        },
    )
    if not isinstance(result, dict):
        raise ValueError("Unexpected non-dict response from map_domain")
    return result


def save_and_push_project_scaffold(
    files: list[dict[str, Any]],
    github_repo_url: str,
    root: str = "generated-project",
    directories: list[str] | None = None,
    commit_message: str = "Initial scaffold commit",
    branch: str = "main",
    github_token: str | None = None,
) -> dict[str, Any]:
    return github_integretion(
        files=files,
        github_repo_url=github_repo_url,
        root=root,
        directories=directories,
        commit_message=commit_message,
        branch=branch,
        github_token=github_token,
    )


@fast_mcp.tool(description="Compatibility hello tool for older clients")
def hello_world() -> str:
    return "Hello World, MCP connected successfully"


def uses_mcp_api_key() -> bool:
    return settings.mcp_auth_mode.strip().lower() == "api_key"


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "mcp_transport_url": f"{settings.public_base_url.rstrip('/')}/mcp/sse",
        "mcp_auth_mode": "api_key" if uses_mcp_api_key() else "none",
    }


@app.middleware("http")
async def require_api_key_for_mcp(request: Request, call_next):
    if uses_mcp_api_key() and request.url.path.startswith("/mcp"):
        x_api_key = request.headers.get("x-api-key")
        if x_api_key != settings.mcp_api_key:
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
    return await call_next(request)


@app.get("/manifest.json")
def manifest() -> dict[str, Any]:
    auth: dict[str, str]
    if uses_mcp_api_key():
        auth = {
            "type": "api_key",
            "in": "header",
            "name": "x-api-key",
        }
    else:
        auth = {"type": "none"}

    return {
        "name": "Local MCP Server",
        "description": "Test MCP connector running locally",
        "version": "1.0",
        "auth": auth,
        "api": {
            "type": "mcp",
            "url": f"{settings.public_base_url.rstrip('/')}/mcp/sse",
        },
    }


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    seed_default_user()


def seed_default_user() -> None:
    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == "admin").first()
        if existing:
            return

        user = User(
            username="admin",
            email="admin@example.com",
            password_hash=get_password_hash("admin123"),
            is_active=True,
        )
        db.add(user)
        db.commit()
    finally:
        db.close()


mcp_sse_app = fast_mcp.sse_app()
mcp_messages_app = next(route.app for route in mcp_sse_app.routes if getattr(route, "path", None) == "/messages")

app.mount("/mcp", mcp_sse_app)
app.mount("/messages", mcp_messages_app)
