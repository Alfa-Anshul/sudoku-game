import json
import os
import subprocess
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from typing import Any
from uuid import uuid4

import httpx

from ..config import get_settings
from .docker_deploy_service import deploy_repo_in_docker, map_domain_to_deployment

BASE_DIR = Path(__file__).resolve().parents[2]
MESSAGES_FILE = BASE_DIR / "messages.json"
settings = get_settings()
PROFESSIONAL_TOP_LEVEL_DIRS = {
    "docs",
    "examples",
    "models",
    "prompts",
    "routes",
    "schemas",
    "scripts",
    "services",
    "template",
    "templates",
    "tests",
    "utils",
}
STRUCTURE_WRAPPER_DIRS = {"api", "app", "backend", "project", "server", "src"}
ROOT_LEVEL_FILES = {
    ".env",
    ".env.example",
    ".gitignore",
    "app.py",
    "docker-compose.yaml",
    "docker-compose.yml",
    "dockerfile",
    "jenkinsfile",
    "license",
    "license.md",
    "main.py",
    "makefile",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "readme.md",
    "requirements.txt",
}
DOCUMENTATION_SUFFIXES = {".md", ".mdx", ".rst"}
SCRIPT_SUFFIXES = {".bat", ".cmd", ".ps1", ".sh"}
TEMPLATE_SUFFIXES = {".html", ".jinja", ".jinja2", ".j2", ".mustache", ".tpl"}


def ensure_messages_file() -> None:
    if not MESSAGES_FILE.exists():
        MESSAGES_FILE.write_text("[]", encoding="utf-8")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_message_record(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        message = item.strip()
        if not message:
            return None
        return {
            "id": str(uuid4()),
            "message": message,
            "received_at": utc_now_iso(),
            "reply": "MCP connected successfully",
            "status": "connected",
            "source": "legacy-local-mcp-server",
        }

    if not isinstance(item, dict):
        return None

    message = str(item.get("message", "")).strip()
    if not message:
        return None

    return {
        "id": str(item.get("id") or uuid4()),
        "message": message,
        "received_at": str(item.get("received_at") or utc_now_iso()),
        "reply": str(item.get("reply") or "MCP connected successfully"),
        "status": str(item.get("status") or "connected"),
        "source": str(item.get("source") or "local-mcp-server"),
    }


def load_messages() -> list[dict[str, Any]]:
    ensure_messages_file()
    try:
        data = json.loads(MESSAGES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(data, list):
        return []

    normalized = [record for item in data if (record := normalize_message_record(item))]
    if normalized != data:
        save_messages(normalized)
    return normalized


def save_messages(messages: list[dict[str, Any]]) -> None:
    MESSAGES_FILE.write_text(json.dumps(messages, ensure_ascii=True, indent=2), encoding="utf-8")


def mirror_message_record(record: dict[str, Any]) -> None:
    if not settings.local_saver_url:
        return

    headers: dict[str, str] = {}
    if settings.local_saver_api_key:
        headers["x-local-saver-key"] = settings.local_saver_api_key

    try:
        with httpx.Client(timeout=3.0) as client:
            client.post(f"{settings.local_saver_url.rstrip('/')}/save", json=record, headers=headers)
    except httpx.HTTPError:
        return


def store_message_record(message: str, source: str) -> tuple[dict[str, Any], int]:
    text = message.strip()
    if not text:
        raise ValueError("message must be a non-empty string")

    record = {
        "id": str(uuid4()),
        "message": text,
        "received_at": utc_now_iso(),
        "reply": "MCP connected successfully",
        "status": "connected",
        "source": source,
    }
    messages = load_messages()
    messages.append(record)
    save_messages(messages)
    mirror_message_record(record)
    return record, len(messages)


def _normalize_relative_posix_path(rel_path: str) -> str:
    raw_parts = [part for part in PurePosixPath(rel_path.replace("\\", "/").strip()).parts if part not in {"", "."}]
    pure_rel = PurePosixPath(*raw_parts)
    if pure_rel.is_absolute() or any(part == ".." for part in pure_rel.parts):
        raise ValueError(f"Unsafe scaffold path: {rel_path}")
    return pure_rel.as_posix()


def _guess_professional_directory(file_name: str) -> str | None:
    lower_name = file_name.lower()
    suffix = Path(lower_name).suffix
    stem = Path(lower_name).stem

    if lower_name in ROOT_LEVEL_FILES or lower_name.startswith("."):
        return None
    if lower_name.startswith("test_") or lower_name.endswith("_test.py") or lower_name.endswith("_spec.py"):
        return "tests"
    if suffix in SCRIPT_SUFFIXES:
        return "scripts"
    if suffix in DOCUMENTATION_SUFFIXES:
        return "docs"
    if suffix in TEMPLATE_SUFFIXES:
        return "templates"
    if suffix == ".ipynb" or lower_name.startswith("example"):
        return "examples"
    if "prompt" in stem:
        return "prompts"
    if stem in {"model", "models"} or stem.endswith("_model"):
        return "models"
    if stem in {"route", "routes", "router", "routers"} or stem.endswith("_route") or stem.endswith("_router"):
        return "routes"
    if stem in {"schema", "schemas"} or stem.endswith("_schema"):
        return "schemas"
    if stem in {"service", "services"} or stem.endswith("_service"):
        return "services"
    if stem in {"template", "templates"}:
        return "templates"
    if stem in {"utils", "util", "helpers", "helper", "common"} or stem.endswith("_util"):
        return "utils"
    return None


def _organize_scaffold_path(rel_path: str) -> str:
    normalized_path = _normalize_relative_posix_path(rel_path)
    pure_rel = PurePosixPath(normalized_path)
    if not pure_rel.parts:
        raise ValueError(f"Unsafe scaffold path: {rel_path}")

    first_part = pure_rel.parts[0].lower()
    if first_part in PROFESSIONAL_TOP_LEVEL_DIRS or pure_rel.parts[0].startswith("."):
        return normalized_path
    if len(pure_rel.parts) > 1 and first_part in STRUCTURE_WRAPPER_DIRS:
        return _organize_scaffold_path(PurePosixPath(*pure_rel.parts[1:]).as_posix())
    if len(pure_rel.parts) > 1:
        return normalized_path

    target_dir = _guess_professional_directory(pure_rel.name)
    if not target_dir:
        return normalized_path
    return PurePosixPath(target_dir, pure_rel.name).as_posix()


def _organize_scaffold_directory(rel_path: str) -> str:
    normalized_path = _normalize_relative_posix_path(rel_path)
    pure_rel = PurePosixPath(normalized_path)
    if not pure_rel.parts:
        raise ValueError(f"Unsafe scaffold path: {rel_path}")

    first_part = pure_rel.parts[0].lower()
    if first_part in PROFESSIONAL_TOP_LEVEL_DIRS or pure_rel.parts[0].startswith("."):
        return normalized_path
    if len(pure_rel.parts) > 1 and first_part in STRUCTURE_WRAPPER_DIRS:
        return _organize_scaffold_directory(PurePosixPath(*pure_rel.parts[1:]).as_posix())
    if len(pure_rel.parts) == 1 and pure_rel.name.lower() in PROFESSIONAL_TOP_LEVEL_DIRS:
        return pure_rel.name
    return normalized_path


def _normalize_scaffold_input(arguments: dict[str, Any]) -> tuple[str, list[str], list[dict[str, str]]]:
    files_raw = arguments.get("files")
    if not isinstance(files_raw, list) or not files_raw:
        raise ValueError("files must be a non-empty list")

    normalized_files: list[dict[str, str]] = []
    for item in files_raw:
        if not isinstance(item, dict):
            continue
        rel_path = item.get("path")
        if not isinstance(rel_path, str) or not rel_path.strip():
            continue
        normalized_files.append(
            {
                "path": _organize_scaffold_path(rel_path.strip()),
                "content": str(item.get("content", "")),
            }
        )

    if not normalized_files:
        raise ValueError("files must contain at least one valid {path, content} item")

    directories_raw = arguments.get("directories", [])
    directories: list[str] = []
    if isinstance(directories_raw, list):
        for value in directories_raw:
            if not isinstance(value, str) or not value.strip():
                continue
            organized_dir = _organize_scaffold_directory(value.strip())
            if organized_dir not in directories:
                directories.append(organized_dir)

    for file_entry in normalized_files:
        parent_dir = str(PurePosixPath(file_entry["path"]).parent)
        if parent_dir not in {"", "."} and parent_dir not in directories:
            directories.append(parent_dir)

    root = str(arguments.get("root") or "generated-project").strip() or "generated-project"
    return root, directories, normalized_files


def _resolve_safe_path(base_dir: Path, rel_path: str) -> Path:
    pure_rel = PurePosixPath(_normalize_relative_posix_path(rel_path))
    return (base_dir / Path(*pure_rel.parts)).resolve()


def _materialize_scaffold(root: str, directories: list[str], files: list[dict[str, str]]) -> tuple[Path, dict[str, int]]:
    target_root = _resolve_safe_path(BASE_DIR, root)
    target_root.mkdir(parents=True, exist_ok=True)

    created_directories = 0
    written_files = 0
    for rel_dir in directories:
        dir_path = _resolve_safe_path(target_root, rel_dir)
        if not dir_path.exists():
            created_directories += 1
        dir_path.mkdir(parents=True, exist_ok=True)

    for file_entry in files:
        file_path = _resolve_safe_path(target_root, file_entry["path"])
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(file_entry["content"], encoding="utf-8")
        written_files += 1

    return target_root, {
        "created_directories": created_directories,
        "written_files": written_files,
    }


def _run_git(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not available in the execution environment") from exc


def _normalize_github_repo_url(repo_url: str) -> str:
    normalized = repo_url.strip()
    if not normalized:
        return normalized

    if normalized.startswith("https://github.com/"):
        return normalized

    shorthand = normalized.strip("/")
    parts = [part for part in shorthand.split("/") if part]
    if len(parts) == 2:
        return f"https://github.com/{parts[0]}/{parts[1]}"

    return normalized


def _parse_github_repo(repo_url: str) -> tuple[str, str]:
    normalized_url = _normalize_github_repo_url(repo_url)
    parsed = urlparse(normalized_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("github_repo_url must be a valid GitHub repo URL like https://github.com/<owner>/<repo> or <owner>/<repo>")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise ValueError("github_repo_url must include owner and repository name")

    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        raise ValueError("github_repo_url must include owner and repository name")
    return owner, repo


def _github_api_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_api_error_message(response: httpx.Response, default_message: str) -> str:
    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        detail = str(payload.get("message") or "").strip()
        raw_errors = payload.get("errors")
        if isinstance(raw_errors, list):
            extra_details: list[str] = []
            for item in raw_errors[:3]:
                if isinstance(item, dict):
                    value = str(item.get("message") or item.get("code") or item.get("field") or "").strip()
                else:
                    value = str(item).strip()
                if value:
                    extra_details.append(value)
            if extra_details:
                detail = f"{detail} ({'; '.join(extra_details)})" if detail else "; ".join(extra_details)

    if not detail:
        detail = response.text[:500].strip()

    if detail:
        return f"{default_message}: {detail}"
    return default_message


def _create_github_repo(
    *,
    name: str,
    token: str,
    owner: str | None = None,
    description: str = "",
    public: bool = True,
    auto_init: bool = False,
    homepage: str | None = None,
) -> dict[str, Any]:
    repo_name = name.strip()
    if not repo_name:
        raise ValueError("name is required to create a GitHub repository.")

    owner_name = (owner or "").strip() or None
    payload: dict[str, Any] = {
        "name": repo_name,
        "description": description.strip(),
        "private": not public,
        "auto_init": auto_init,
    }
    homepage_url = (homepage or "").strip()
    if homepage_url:
        payload["homepage"] = homepage_url

    endpoint = "https://api.github.com/user/repos"
    if owner_name:
        endpoint = f"https://api.github.com/orgs/{owner_name}/repos"

    with httpx.Client(timeout=30.0, headers=_github_api_headers(token)) as client:
        response = client.post(endpoint, json=payload)

    if response.status_code == 201:
        data = response.json()
        return {
            "created": True,
            "github_repo_url": str(data.get("html_url") or ""),
            "clone_url": str(data.get("clone_url") or ""),
            "ssh_url": str(data.get("ssh_url") or ""),
            "owner": str((data.get("owner") or {}).get("login") or owner_name or ""),
            "name": str(data.get("name") or repo_name),
            "full_name": str(data.get("full_name") or ""),
            "private": bool(data.get("private", not public)),
            "default_branch": str(data.get("default_branch") or "main"),
        }

    if response.status_code == 401:
        raise ValueError("GitHub token is invalid or expired.")
    if response.status_code == 403:
        raise ValueError(_github_api_error_message(response, "GitHub refused repository creation"))
    if response.status_code == 422:
        raise ValueError(
            _github_api_error_message(
                response,
                "GitHub repository could not be created. It may already exist or the name may be invalid",
            )
        )
    raise RuntimeError(_github_api_error_message(response, "GitHub repository creation failed"))


def _push_to_github_via_api(
    *,
    project_dir: Path,
    repo_url: str,
    token: str,
    commit_message: str,
    branch: str,
) -> dict[str, Any]:
    owner, repo = _parse_github_repo(repo_url)
    api_base = f"https://api.github.com/repos/{owner}/{repo}/contents"

    uploaded_files = 0
    with httpx.Client(timeout=30.0, headers=_github_api_headers(token)) as client:
        repo_response = client.get(f"https://api.github.com/repos/{owner}/{repo}")
        if repo_response.status_code == 404:
            raise ValueError(
                "GitHub repository was not found or this token cannot access it. Create it first with create_repo "
                "or provide an existing github_repo_url."
            )
        if repo_response.status_code not in {200}:
            raise RuntimeError(_github_api_error_message(repo_response, "GitHub repository lookup failed"))

        for path in sorted(project_dir.rglob("*")):
            if not path.is_file():
                continue
            if ".git" in path.parts:
                continue

            relative_path = path.relative_to(project_dir).as_posix()
            endpoint = f"{api_base}/{relative_path}"

            existing_sha: str | None = None
            get_resp = client.get(endpoint, params={"ref": branch})
            if get_resp.status_code == 200:
                existing_sha = str(get_resp.json().get("sha") or "") or None
            elif get_resp.status_code != 404:
                raise RuntimeError(
                    f"GitHub API lookup failed for {relative_path}: {get_resp.status_code}"
                )

            encoded_content = b64encode(path.read_bytes()).decode("ascii")
            payload: dict[str, Any] = {
                "message": commit_message,
                "content": encoded_content,
                "branch": branch,
            }
            if existing_sha:
                payload["sha"] = existing_sha

            put_resp = client.put(endpoint, json=payload)
            if put_resp.status_code not in {200, 201}:
                raise RuntimeError(
                    _github_api_error_message(
                        put_resp,
                        f"GitHub API upload failed for {relative_path}",
                    )
                )
            uploaded_files += 1

    return {
        "committed": uploaded_files > 0,
        "remote": repo_url,
        "branch": branch,
        "push_stdout": f"Uploaded {uploaded_files} file(s) via GitHub API",
        "push_stderr": "",
    }


def _read_env_value(key: str) -> str:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return ""

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            current_key, value = line.split("=", 1)
            if current_key.strip() != key:
                continue
            return _sanitize_github_token(value)
    except OSError:
        return ""

    return ""


def _resolve_github_token(payload_token: Any = None) -> str:
    token = _sanitize_github_token(payload_token)
    if not token:
        token = _sanitize_github_token(settings.github_token)
    if not token:
        token = _sanitize_github_token(os.getenv("GITHUB_TOKEN", ""))
    if not token:
        token = _read_env_value("GITHUB_TOKEN")
    if not token:
        raise ValueError(
            "GitHub token is not configured. Set GITHUB_TOKEN in the runtime environment or in the repo .env file."
        )
    return token


def _best_effort_github_token(payload_token: Any = None) -> str:
    try:
        return _resolve_github_token(payload_token)
    except ValueError:
        return ""


def _sanitize_github_token(raw_token: Any) -> str:
    token = str(raw_token or "").strip()
    if len(token) >= 2 and ((token[0] == '"' and token[-1] == '"') or (token[0] == "'" and token[-1] == "'")):
        token = token[1:-1].strip()
    return token


def _push_to_github(project_dir: Path, repo_url: str, token: str, commit_message: str, branch: str) -> dict[str, Any]:
    normalized_repo_url = _normalize_github_repo_url(repo_url)
    if not normalized_repo_url.startswith("https://github.com/"):
        raise ValueError("github_repo_url must be a valid GitHub repo URL like https://github.com/<owner>/<repo> or <owner>/<repo>")

    if not _sanitize_github_token(token):
        raise ValueError(
            "GitHub token is not configured. Set GITHUB_TOKEN in the runtime environment or in the repo .env file."
        )

    try:
        git_dir = project_dir / ".git"
        if not git_dir.exists():
            _run_git(["init"], cwd=project_dir)

        _run_git(["add", "."], cwd=project_dir)

        status = _run_git(["status", "--porcelain"], cwd=project_dir).stdout.strip()
        committed = False
        if status:
            try:
                _run_git(["commit", "-m", commit_message], cwd=project_dir)
            except subprocess.CalledProcessError:
                _run_git(["config", "user.name", "MCP Bot"], cwd=project_dir)
                _run_git(["config", "user.email", "mcp-bot@example.local"], cwd=project_dir)
                _run_git(["commit", "-m", commit_message], cwd=project_dir)
            committed = True

        _run_git(["branch", "-M", branch], cwd=project_dir)

        remote_name = "origin"
        try:
            _run_git(["remote", "get-url", remote_name], cwd=project_dir)
            _run_git(["remote", "set-url", remote_name, normalized_repo_url], cwd=project_dir)
        except subprocess.CalledProcessError:
            _run_git(["remote", "add", remote_name, normalized_repo_url], cwd=project_dir)

        basic_auth = b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
        header = f"AUTHORIZATION: basic {basic_auth}"

        push_result = _run_git(
            ["-c", f"http.https://github.com/.extraheader={header}", "push", "-u", remote_name, branch],
            cwd=project_dir,
        )

        return {
            "committed": committed,
            "remote": normalized_repo_url,
            "branch": branch,
            "push_stdout": push_result.stdout.strip(),
            "push_stderr": push_result.stderr.strip(),
        }
    except (RuntimeError, subprocess.CalledProcessError):
        return _push_to_github_via_api(
            project_dir=project_dir,
            repo_url=normalized_repo_url,
            token=token,
            commit_message=commit_message,
            branch=branch,
        )


def run_local_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | str:
    if tool_name == "hello_world":
        return "Hello World, MCP connected successfully"

    if tool_name in {"write_message", "save_message"}:
        message = arguments.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string")

        record, count = store_message_record(message, source=tool_name)
        if tool_name == "write_message":
            return {
                "status": "connected",
                "reply": record["reply"],
                "stored": True,
                "count": count,
                "record": record,
            }
        return {"saved": True, "count": count, "record": record}

    if tool_name in {"read_message", "get_messages"}:
        messages = load_messages()
        return {"messages": messages, "count": len(messages)}

    if tool_name == "save_project_scaffold":
        repo_url = str(arguments.get("github_repo_url") or "").strip()
        token = _sanitize_github_token(arguments.get("github_token"))
        if repo_url and (
            token
            or _sanitize_github_token(settings.github_token)
            or _sanitize_github_token(os.getenv("GITHUB_TOKEN", ""))
            or _read_env_value("GITHUB_TOKEN")
        ):
            return run_local_mcp_tool("github_integretion", arguments)

        root, directories, normalized_files = _normalize_scaffold_input(arguments)
        scaffold = {
            "scaffold": {
                "root": root,
                "directories": directories,
                "files": normalized_files,
            }
        }
        record, count = store_message_record(
            json.dumps(scaffold, ensure_ascii=True, indent=2),
            source="local-mcp:save_project_scaffold",
        )
        return {
            "saved": True,
            "count": count,
            "record_id": record["id"],
            "root": root,
            "files": len(normalized_files),
            "directories": len(directories),
        }

    if tool_name == "create_repo":
        repo_name = str(arguments.get("name") or "").strip()
        owner = str(arguments.get("owner") or "").strip() or None
        description = str(arguments.get("description") or "")
        homepage = str(arguments.get("homepage") or "").strip() or None
        public = bool(arguments.get("public", True))
        auto_init = bool(arguments.get("auto_init", False))
        token = _resolve_github_token(arguments.get("github_token"))
        result = _create_github_repo(
            name=repo_name,
            token=token,
            owner=owner,
            description=description,
            public=public,
            auto_init=auto_init,
            homepage=homepage,
        )

        safe_payload = {
            "repo": {
                "name": repo_name,
                "owner": owner,
                "description": description,
                "homepage": homepage,
                "public": public,
                "auto_init": auto_init,
                "github_repo_url": result["github_repo_url"],
            }
        }
        record, count = store_message_record(
            json.dumps(safe_payload, ensure_ascii=True, indent=2),
            source="local-mcp:create_repo",
        )
        result["record_id"] = record["id"]
        result["count"] = count
        return result

    if tool_name in {"github_integretion", "save_and_push_project_scaffold"}:
        root, directories, normalized_files = _normalize_scaffold_input(arguments)
        repo_url = str(arguments.get("github_repo_url") or "").strip()
        token = _resolve_github_token(arguments.get("github_token"))
        branch = str(arguments.get("branch") or "main").strip() or "main"
        commit_message = str(arguments.get("commit_message") or "Initial scaffold commit").strip()
        if not commit_message:
            commit_message = "Initial scaffold commit"

        project_dir, materialize_stats = _materialize_scaffold(
            root=root,
            directories=directories,
            files=normalized_files,
        )
        push_stats = _push_to_github(
            project_dir=project_dir,
            repo_url=repo_url,
            token=token,
            commit_message=commit_message,
            branch=branch,
        )

        safe_payload = {
            "scaffold": {
                "root": root,
                "directories": directories,
                "files": normalized_files,
            },
            "git": {
                "github_repo_url": repo_url,
                "branch": branch,
                "commit_message": commit_message,
            },
        }
        record, count = store_message_record(
            json.dumps(safe_payload, ensure_ascii=True, indent=2),
            source="local-mcp:save_and_push_project_scaffold",
        )

        return {
            "saved": True,
            "pushed": True,
            "count": count,
            "record_id": record["id"],
            "root": root,
            "project_dir": str(project_dir),
            "files": len(normalized_files),
            "directories": len(directories),
            "branch": push_stats["branch"],
            "remote": push_stats["remote"],
            "committed": push_stats["committed"],
            "created_directories": materialize_stats["created_directories"],
            "written_files": materialize_stats["written_files"],
            "push_stdout": push_stats["push_stdout"],
            "push_stderr": push_stats["push_stderr"],
        }

    if tool_name == "deploy_inDocker":
        repo_url = str(arguments.get("github_repo_url") or "").strip()
        branch = str(arguments.get("branch") or "main").strip() or "main"
        app_name = str(arguments.get("app_name") or "").strip() or None
        fastapi_module = str(arguments.get("fastapi_module") or "").strip() or None
        public_host = (
            str(arguments.get("public_host") or arguments.get("deploy_public_host") or "").strip() or None
        )
        deploy_ssh_host = str(arguments.get("deploy_ssh_host") or "").strip() or None
        deploy_ssh_user = str(arguments.get("deploy_ssh_user") or "").strip() or None
        deploy_ssh_port_raw = arguments.get("deploy_ssh_port")
        deploy_ssh_port = int(deploy_ssh_port_raw) if deploy_ssh_port_raw not in (None, "") else None
        deploy_ssh_key_path = str(arguments.get("deploy_ssh_key_path") or "").strip() or None
        deploy_ssh_private_key = str(arguments.get("deploy_ssh_private_key") or "") or None
        deploy_docker_command = str(arguments.get("deploy_docker_command") or "").strip() or None
        result = deploy_repo_in_docker(
            github_repo_url=repo_url,
            branch=branch,
            app_name=app_name,
            fastapi_module=fastapi_module,
            public_host=public_host,
            deploy_ssh_host=deploy_ssh_host,
            deploy_ssh_user=deploy_ssh_user,
            deploy_ssh_port=deploy_ssh_port,
            deploy_ssh_key_path=deploy_ssh_key_path,
            deploy_ssh_private_key=deploy_ssh_private_key,
            deploy_docker_command=deploy_docker_command,
            github_token=_best_effort_github_token(arguments.get("github_token")),
        )

        safe_payload = {
            "deploy": {
                "github_repo_url": repo_url,
                "branch": branch,
                "app_name": app_name,
                "fastapi_module": fastapi_module,
                "public_host": public_host,
                "deploy_public_host": public_host,
                "deploy_ssh_host": deploy_ssh_host,
                "deploy_ssh_user": deploy_ssh_user,
                "deploy_ssh_port": deploy_ssh_port,
                "deploy_ssh_key_path": deploy_ssh_key_path,
                "deploy_docker_command": deploy_docker_command,
            }
        }
        record, count = store_message_record(
            json.dumps(safe_payload, ensure_ascii=True, indent=2),
            source="local-mcp:deploy_inDocker",
        )
        result["record_id"] = record["id"]
        result["count"] = count
        return result

    if tool_name == "map_domain":
        domain = str(arguments.get("domain") or "").strip()
        container_name = str(arguments.get("container_name") or "").strip() or None
        port_raw = arguments.get("port")
        port = int(port_raw) if port_raw not in (None, "") else None
        docs_path = str(arguments.get("docs_path") or "/docs").strip() or "/docs"
        deploy_ssh_host = str(arguments.get("deploy_ssh_host") or "").strip() or None
        deploy_ssh_user = str(arguments.get("deploy_ssh_user") or "").strip() or None
        deploy_ssh_port_raw = arguments.get("deploy_ssh_port")
        deploy_ssh_port = int(deploy_ssh_port_raw) if deploy_ssh_port_raw not in (None, "") else None
        deploy_ssh_key_path = str(arguments.get("deploy_ssh_key_path") or "").strip() or None
        deploy_ssh_private_key = str(arguments.get("deploy_ssh_private_key") or "") or None
        deploy_docker_command = str(arguments.get("deploy_docker_command") or "").strip() or None
        certbot_email = str(arguments.get("certbot_email") or "").strip() or None
        hostinger_api_token = str(arguments.get("hostinger_api_token") or "")
        # Auto-derive zone domain from the subdomain if not explicitly provided
        # e.g. tic_tactoe.anervera.live → zone = anervera.live
        raw_zone = str(arguments.get("hostinger_zone_domain") or "").strip()
        if not raw_zone and domain:
            parts = domain.strip().lower().split(".")
            raw_zone = ".".join(parts[-2:]) if len(parts) >= 3 else domain.strip().lower()
        hostinger_zone_domain = raw_zone or None
        dns_target_ip = str(arguments.get("dns_target_ip") or "").strip() or None
        # Auto-infer dns_target_ip from deploy_ssh_host if not explicitly provided
        if not dns_target_ip and deploy_ssh_host:
            dns_target_ip = deploy_ssh_host.strip()
        include_www_alias = bool(arguments.get("include_www_alias", True))
        enable_https = bool(arguments.get("enable_https", True))

        result = map_domain_to_deployment(
            domain=domain,
            container_name=container_name,
            port=port,
            docs_path=docs_path,
            deploy_ssh_host=deploy_ssh_host,
            deploy_ssh_user=deploy_ssh_user,
            deploy_ssh_port=deploy_ssh_port,
            deploy_ssh_key_path=deploy_ssh_key_path,
            deploy_ssh_private_key=deploy_ssh_private_key,
            deploy_docker_command=deploy_docker_command,
            certbot_email=certbot_email,
            hostinger_api_token=hostinger_api_token,
            hostinger_zone_domain=hostinger_zone_domain,
            dns_target_ip=dns_target_ip,
            include_www_alias=include_www_alias,
            enable_https=enable_https,
        )

        safe_payload = {
            "domain": {
                "domain": domain,
                "container_name": container_name,
                "port": port,
                "docs_path": docs_path,
                "deploy_ssh_host": deploy_ssh_host,
                "deploy_ssh_user": deploy_ssh_user,
                "deploy_ssh_port": deploy_ssh_port,
                "deploy_ssh_key_path": deploy_ssh_key_path,
                "deploy_docker_command": deploy_docker_command,
                "certbot_email": certbot_email,
                "hostinger_zone_domain": hostinger_zone_domain,
                "dns_target_ip": dns_target_ip,
                "include_www_alias": include_www_alias,
                "enable_https": enable_https,
            }
        }
        record, count = store_message_record(
            json.dumps(safe_payload, ensure_ascii=True, indent=2),
            source="local-mcp:map_domain",
        )
        result["record_id"] = record["id"]
        result["count"] = count
        return result

    raise ValueError(f"Unknown tool: {tool_name}")
