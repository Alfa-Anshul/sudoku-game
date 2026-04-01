import json
from typing import Any, Awaitable, Callable

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import Note, User
from .local_mcp_service import run_local_mcp_tool, store_message_record

TOOLS = [
    {
        "name": "health_check",
        "description": "Check whether core services are reachable",
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_user",
        "description": "Fetch user profile by user ID",
        "input_schema": {
            "type": "object",
            "properties": {"user_id": {"type": "integer", "minimum": 1}},
            "required": ["user_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "save_note",
        "description": "Save a note for a user",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "minimum": 1},
                "title": {"type": "string", "minLength": 1},
                "content": {"type": "string", "minLength": 1},
            },
            "required": ["user_id", "title", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_notes",
        "description": "Search a user's notes by query text",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "minimum": 1},
                "query": {"type": "string", "minLength": 1},
            },
            "required": ["user_id", "query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "call_external_api",
        "description": "Call an external HTTP API endpoint",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "format": "uri"},
                "method": {"type": "string", "enum": ["GET", "POST"]},
                "params": {"type": "object"},
                "json": {"type": "object"},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "send_email",
        "description": "Send an email message (stub transport)",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string", "minLength": 1},
                "body": {"type": "string", "minLength": 1},
            },
            "required": ["to", "subject", "body"],
            "additionalProperties": False,
        },
    },
    {
        "name": "save_project_scaffold",
        "description": "Save scaffold payload locally, or push it to GitHub as well when github_repo_url is provided. Use create_repo first if the repository does not exist yet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "minLength": 1},
                "directories": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
                "files": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "minLength": 1},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                        "additionalProperties": False,
                    },
                },
                "github_repo_url": {"type": "string", "format": "uri"},
                "commit_message": {"type": "string", "minLength": 1},
                "branch": {"type": "string", "minLength": 1},
                "github_token": {"type": "string", "minLength": 1},
            },
            "required": ["files"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_repo",
        "description": "Create a GitHub repository using GITHUB_TOKEN from runtime environment or .env. Repositories are public by default.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "owner": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
                "homepage": {"type": "string", "format": "uri"},
                "public": {"type": "boolean"},
                "auto_init": {"type": "boolean"},
                "github_token": {"type": "string", "minLength": 1},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "github_integretion",
        "description": "Create scaffold files locally, commit them, and push to GitHub using GITHUB_TOKEN from runtime environment or .env (or an optional github_token argument). Use create_repo first if the repository does not exist yet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "minLength": 1},
                "directories": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
                "files": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "minLength": 1},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                        "additionalProperties": False,
                    },
                },
                "github_repo_url": {"type": "string", "format": "uri"},
                "commit_message": {"type": "string", "minLength": 1},
                "branch": {"type": "string", "minLength": 1},
                "github_token": {"type": "string", "minLength": 1},
            },
            "required": ["files", "github_repo_url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "deploy_inDocker",
        "description": "Clone a GitHub repository onto the configured host over SSH, deploy its FastAPI app in Docker, and when the repo contains a buildable frontend (for example React/Vite in frontend/) serve that interactive frontend from the returned public URL. Connection settings come from backend runtime env or can be passed in the tool input.",
        "input_schema": {
            "type": "object",
            "properties": {
                "github_repo_url": {"type": "string", "minLength": 1},
                "branch": {"type": "string", "minLength": 1},
                "app_name": {"type": "string", "minLength": 1},
                "fastapi_module": {"type": "string", "minLength": 1},
                "public_host": {"type": "string", "minLength": 1},
                "deploy_public_host": {"type": "string", "minLength": 1},
                "deploy_ssh_host": {"type": "string", "minLength": 1},
                "deploy_ssh_user": {"type": "string", "minLength": 1},
                "deploy_ssh_port": {"type": "integer", "minimum": 1},
                "deploy_ssh_key_path": {"type": "string", "minLength": 1},
                "deploy_ssh_private_key": {"type": "string", "minLength": 1},
                "deploy_docker_command": {"type": "string", "minLength": 1},
            },
            "required": ["github_repo_url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "map_domain",
        "description": "Map a deployed Dockerized app to a domain using nginx, optionally issue TLS certificates, and optionally sync DNS records through the Hostinger API.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "minLength": 1},
                "container_name": {"type": "string", "minLength": 1},
                "port": {"type": "integer", "minimum": 1},
                "docs_path": {"type": "string", "minLength": 1},
                "deploy_ssh_host": {"type": "string", "minLength": 1},
                "deploy_ssh_user": {"type": "string", "minLength": 1},
                "deploy_ssh_port": {"type": "integer", "minimum": 1},
                "deploy_ssh_key_path": {"type": "string", "minLength": 1},
                "deploy_ssh_private_key": {"type": "string", "minLength": 1},
                "deploy_docker_command": {"type": "string", "minLength": 1},
                "certbot_email": {"type": "string", "minLength": 1},
                "hostinger_api_token": {"type": "string", "minLength": 1},
                "hostinger_zone_domain": {"type": "string", "minLength": 1},
                "dns_target_ip": {"type": "string", "minLength": 1},
                "include_www_alias": {"type": "boolean"},
                "enable_https": {"type": "boolean"}
            },
            "required": ["domain"],
            "additionalProperties": False,
        },
    },
]


async def health_check(_: dict[str, Any], __: Session | None = None) -> dict[str, Any]:
    return {"status": "ok", "backend_status": {"status": "ok", "service": "backend"}}


async def get_user(payload: dict[str, Any], db: Session | None = None) -> dict[str, Any]:
    if db is None:
        raise ValueError("db session is required")

    user = db.query(User).filter(User.id == int(payload["user_id"])).first()
    if not user:
        raise ValueError("User not found")

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
    }


async def save_note(payload: dict[str, Any], db: Session | None = None) -> dict[str, Any]:
    if db is None:
        raise ValueError("db session is required")

    note = Note(
        user_id=int(payload["user_id"]),
        title=str(payload["title"]),
        content=str(payload["content"]),
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"id": note.id, "title": note.title, "content": note.content}


async def search_notes(payload: dict[str, Any], db: Session | None = None) -> dict[str, Any]:
    if db is None:
        raise ValueError("db session is required")

    user_id = int(payload["user_id"])
    query = str(payload["query"])
    notes = (
        db.query(Note)
        .filter(
            Note.user_id == user_id,
            or_(Note.title.ilike(f"%{query}%"), Note.content.ilike(f"%{query}%")),
        )
        .all()
    )
    return {
        "results": [{"id": note.id, "title": note.title, "content": note.content} for note in notes],
        "count": len(notes),
    }


async def call_external_api(payload: dict[str, Any], __: Session | None = None) -> dict[str, Any]:
    method = str(payload.get("method", "GET")).upper()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.request(
            method=method,
            url=str(payload["url"]),
            params=payload.get("params") or None,
            json=payload.get("json") or None,
        )
    return {
        "status_code": resp.status_code,
        "body": resp.text[:4000],
        "headers": dict(resp.headers),
    }


async def send_email(payload: dict[str, Any], __: Session | None = None) -> dict[str, Any]:
    return {
        "status": "queued",
        "transport": "stub",
        "to": str(payload["to"]),
        "subject": str(payload["subject"]),
    }


async def save_project_scaffold(payload: dict[str, Any], __: Session | None = None) -> dict[str, Any]:
    repo_url = str(payload.get("github_repo_url") or "").strip()
    if repo_url:
        result = run_local_mcp_tool("github_integretion", payload)
        if not isinstance(result, dict):
            raise ValueError("Unexpected non-dict response from github_integretion")
        return result

    files_raw = payload.get("files")
    if not isinstance(files_raw, list) or not files_raw:
        raise ValueError("files must be a non-empty list")

    normalized_files: list[dict[str, str]] = []
    for item in files_raw:
        if not isinstance(item, dict):
            continue
        rel_path = item.get("path")
        if not isinstance(rel_path, str) or not rel_path.strip():
            continue
        content = item.get("content", "")
        normalized_files.append({"path": rel_path.strip(), "content": str(content)})

    if not normalized_files:
        raise ValueError("files must contain at least one valid {path, content} item")

    directories_raw = payload.get("directories", [])
    directories = (
        [value.strip() for value in directories_raw if isinstance(value, str) and value.strip()]
        if isinstance(directories_raw, list)
        else []
    )

    root = payload.get("root", "generated-project")
    root_text = str(root).strip() if root is not None else "generated-project"
    if not root_text:
        root_text = "generated-project"

    scaffold = {
        "scaffold": {
            "root": root_text,
            "directories": directories,
            "files": normalized_files,
        }
    }
    record, count = store_message_record(
        json.dumps(scaffold, ensure_ascii=True, indent=2),
        source="tool:save_project_scaffold",
    )
    return {
        "saved": True,
        "count": count,
        "record_id": record["id"],
        "root": root_text,
        "files": len(normalized_files),
        "directories": len(directories),
    }


async def create_repo(payload: dict[str, Any], __: Session | None = None) -> dict[str, Any]:
    result = run_local_mcp_tool("create_repo", payload)
    if not isinstance(result, dict):
        raise ValueError("Unexpected non-dict response from create_repo")
    return result


async def github_integretion(payload: dict[str, Any], __: Session | None = None) -> dict[str, Any]:
    result = run_local_mcp_tool("github_integretion", payload)
    if not isinstance(result, dict):
        raise ValueError("Unexpected non-dict response from github_integretion")
    return result


async def deploy_inDocker(payload: dict[str, Any], __: Session | None = None) -> dict[str, Any]:
    result = run_local_mcp_tool("deploy_inDocker", payload)
    if not isinstance(result, dict):
        raise ValueError("Unexpected non-dict response from deploy_inDocker")
    return result


async def map_domain(payload: dict[str, Any], __: Session | None = None) -> dict[str, Any]:
    result = run_local_mcp_tool("map_domain", payload)
    if not isinstance(result, dict):
        raise ValueError("Unexpected non-dict response from map_domain")
    return result


async def save_and_push_project_scaffold(payload: dict[str, Any], __: Session | None = None) -> dict[str, Any]:
    return await github_integretion(payload, __)


TOOL_REGISTRY: dict[str, Callable[[dict[str, Any], Session | None], Awaitable[dict[str, Any]]]] = {
    "health_check": health_check,
    "get_user": get_user,
    "save_note": save_note,
    "search_notes": search_notes,
    "call_external_api": call_external_api,
    "send_email": send_email,
    "save_project_scaffold": save_project_scaffold,
    "create_repo": create_repo,
    "github_integretion": github_integretion,
    "deploy_inDocker": deploy_inDocker,
    "map_domain": map_domain,
    "save_and_push_project_scaffold": save_and_push_project_scaffold,
}


async def execute_tool(tool_name: str, tool_input: dict[str, Any], db: Session, user_id: int | None = None) -> dict[str, Any]:
    func = TOOL_REGISTRY.get(tool_name)
    if not func:
        raise ValueError(f"Unknown tool: {tool_name}")

    merged_input = dict(tool_input)
    if user_id is not None and "user_id" not in merged_input:
        merged_input["user_id"] = user_id

    return await func(merged_input, db)
