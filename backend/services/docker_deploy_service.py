from __future__ import annotations

import base64
import io
import json
import re
import shlex
import socket
import stat
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import httpx
import paramiko

from ..config import get_settings

BASE_DIR = Path(__file__).resolve().parents[2]
COMMON_FASTAPI_CANDIDATES: list[tuple[str, str]] = [
    ("backend/main.py", "backend.main:app"),
    ("backend/backend.py", "backend.backend:app"),
    ("backend/app.py", "backend.app:app"),
    ("main.py", "main:app"),
    ("app/main.py", "app.main:app"),
    ("app.py", "app:app"),
]
COMMON_REQUIREMENTS_FILES = [
    "backend/requirements.txt",
    "requirements.txt",
]
COMMON_FRONTEND_PACKAGE_CANDIDATES = [
    "frontend/package.json",
    "client/package.json",
    "web/package.json",
    "ui/package.json",
    "package.json",
]
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}


def deploy_repo_in_docker(
    *,
    github_repo_url: str,
    branch: str = "main",
    app_name: str | None = None,
    fastapi_module: str | None = None,
    public_host: str | None = None,
    deploy_ssh_host: str | None = None,
    deploy_ssh_user: str | None = None,
    deploy_ssh_port: int | None = None,
    deploy_ssh_key_path: str | None = None,
    deploy_ssh_private_key: str | None = None,
    deploy_docker_command: str | None = None,
    github_token: str = "",
) -> dict[str, Any]:
    settings = get_settings()

    repo_url = _normalize_github_repo_url(github_repo_url)
    owner, repo = _parse_github_repo(repo_url)
    ssh_host = (deploy_ssh_host or settings.deploy_ssh_host).strip()
    if not ssh_host:
        raise ValueError("DEPLOY_SSH_HOST is not configured.")

    ssh_user = (deploy_ssh_user or settings.deploy_ssh_user).strip() or "ubuntu"
    ssh_port = int(deploy_ssh_port or settings.deploy_ssh_port)
    deploy_root = str(PurePosixPath(settings.deploy_base_dir.strip() or "/opt/mcp-deployments"))
    docker_command = _normalize_shell_command(deploy_docker_command or settings.deploy_docker_command)
    scheme = settings.deploy_public_scheme.strip() or "http"
    resolved_public_host = (public_host or settings.deploy_public_host or ssh_host).strip()
    if not resolved_public_host:
        raise ValueError("DEPLOY_PUBLIC_HOST is not configured.")

    slug = _slugify(app_name or repo)
    container_name = _trim_name(f"mcp-deploy-{slug}")
    image_name = container_name
    remote_project_dir = str(PurePosixPath(deploy_root) / slug)

    ssh = _connect_ssh(
        host=ssh_host,
        port=ssh_port,
        username=ssh_user,
        key_path=deploy_ssh_key_path or settings.deploy_ssh_key_path,
        private_key=deploy_ssh_private_key or settings.deploy_ssh_private_key,
    )
    try:
        _sync_repo_on_remote(
            ssh=ssh,
            repo_url=repo_url,
            branch=branch.strip() or "main",
            remote_project_dir=remote_project_dir,
            github_token=github_token,
        )

        sftp = ssh.open_sftp()
        try:
            resolved_fastapi_module = (
                fastapi_module.strip()
                if isinstance(fastapi_module, str) and fastapi_module.strip()
                else _detect_fastapi_module(sftp, remote_project_dir)
            )
            frontend_project = _detect_frontend_project(sftp, remote_project_dir)
            runtime_module = resolved_fastapi_module
            if frontend_project:
                _write_remote_text(
                    sftp,
                    str(PurePosixPath(remote_project_dir) / "mcp_frontend_wrapper.py"),
                    _render_frontend_wrapper(fastapi_module=resolved_fastapi_module),
                )
                runtime_module = "mcp_frontend_wrapper:app"
            requirements_file = _detect_requirements_file(sftp, remote_project_dir)
            dockerfile_path = str(PurePosixPath(remote_project_dir) / ".mcp-deploy" / "Dockerfile")
            _write_remote_text(
                sftp,
                dockerfile_path,
                _render_dockerfile(
                    fastapi_module=runtime_module,
                    requirements_file=requirements_file,
                    frontend_package_dir=frontend_project["package_dir"] if frontend_project else None,
                ),
            )
        finally:
            sftp.close()

        existing_port = _get_existing_container_port(ssh, docker_command, container_name)
        host_port = existing_port or _find_open_remote_port(
            ssh,
            start=int(settings.deploy_port_start),
            end=int(settings.deploy_port_end),
        )

        _build_and_run_container(
            ssh=ssh,
            docker_command=docker_command,
            remote_project_dir=remote_project_dir,
            dockerfile_path=str(PurePosixPath(remote_project_dir) / ".mcp-deploy" / "Dockerfile"),
            image_name=image_name,
            container_name=container_name,
            host_port=host_port,
        )
        _wait_for_fastapi(
            ssh=ssh,
            docker_command=docker_command,
            container_name=container_name,
            host_port=host_port,
        )

        public_url = f"{scheme}://{resolved_public_host}:{host_port}"
        return {
            "deployed": True,
            "github_repo_url": repo_url,
            "repo_owner": owner,
            "repo_name": repo,
            "branch": branch.strip() or "main",
            "app_name": slug,
            "remote_project_dir": remote_project_dir,
            "container_name": container_name,
            "image_name": image_name,
            "fastapi_module": resolved_fastapi_module,
            "runtime_module": runtime_module,
            "requirements_file": requirements_file,
            "frontend_enabled": bool(frontend_project),
            "frontend_package_dir": frontend_project["package_dir"] if frontend_project else None,
            "public_url": public_url,
            "docs_url": f"{public_url}/docs",
            "port": host_port,
        }
    finally:
        ssh.close()


def map_domain_to_deployment(
    *,
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
    hostinger_api_token: str = "",
    hostinger_zone_domain: str | None = None,
    dns_target_ip: str | None = None,
    include_www_alias: bool = True,
    enable_https: bool = True,
) -> dict[str, Any]:
    """
    Full domain mapping flow:
      1. Sync Hostinger DNS (if token provided) — FIRST so propagation starts early
      2. Wait for DNS propagation to the server IP
      3. Install nginx + write reverse-proxy config
      4. Run certbot for TLS ONLY after DNS is confirmed pointing to the server
      5. Return full status including warnings for every step that was skipped/failed
    """
    settings = get_settings()
    steps: list[dict[str, Any]] = []

    normalized_domain = _normalize_domain(domain)
    normalized_docs_path = _normalize_docs_path(docs_path)
    ssh_host = (deploy_ssh_host or settings.deploy_ssh_host).strip()
    if not ssh_host:
        raise ValueError("DEPLOY_SSH_HOST is not configured.")

    ssh_user = (deploy_ssh_user or settings.deploy_ssh_user).strip() or "ubuntu"
    ssh_port = int(deploy_ssh_port or settings.deploy_ssh_port)
    docker_command = _normalize_shell_command(deploy_docker_command or settings.deploy_docker_command)
    resolved_zone_domain = _normalize_domain(hostinger_zone_domain or normalized_domain)
    resolved_dns_target_ip = (dns_target_ip or ssh_host).strip()
    if not resolved_dns_target_ip:
        raise ValueError("dns_target_ip could not be resolved.")

    resolved_hostinger_api_token = (hostinger_api_token or settings.hostinger_api_token).strip()

    # ── STEP 1: Hostinger DNS sync (before anything else so propagation starts) ──
    hostinger_result: dict[str, Any] = {
        "checked": False,
        "updated": False,
        "zone_domain": resolved_zone_domain,
        "skipped_reason": None,
    }
    if resolved_hostinger_api_token:
        try:
            hostinger_result = _sync_hostinger_dns(
                domain=normalized_domain,
                zone_domain=resolved_zone_domain,
                target_ip=resolved_dns_target_ip,
                api_token=resolved_hostinger_api_token,
                include_www_alias=include_www_alias,
            )
            steps.append({"step": "hostinger_dns_sync", "status": "ok"})
        except Exception as exc:
            # Non-fatal: log the error and continue; the domain may already be configured
            hostinger_result["error"] = str(exc)
            hostinger_result["skipped_reason"] = "Hostinger API call failed — continuing without DNS update"
            steps.append({"step": "hostinger_dns_sync", "status": "warning", "detail": str(exc)})
    else:
        hostinger_result["skipped_reason"] = "No Hostinger API token provided"
        steps.append({"step": "hostinger_dns_sync", "status": "skipped", "detail": "no token"})

    # ── STEP 2: Wait for DNS propagation to the server IP ──
    dns_result = _wait_for_dns_propagation(
        domain=normalized_domain,
        target_ip=resolved_dns_target_ip,
        max_wait_seconds=180,
    )
    steps.append({
        "step": "dns_propagation",
        "status": "ok" if dns_result["matches_target"] else "warning",
        "detail": dns_result,
    })

    # ── STEP 3: Connect SSH, resolve port, install nginx ──
    ssh = _connect_ssh(
        host=ssh_host,
        port=ssh_port,
        username=ssh_user,
        key_path=deploy_ssh_key_path or settings.deploy_ssh_key_path,
        private_key=deploy_ssh_private_key or settings.deploy_ssh_private_key,
    )
    try:
        resolved_container_name = container_name.strip() if isinstance(container_name, str) and container_name.strip() else None
        resolved_port = int(port) if port is not None else None
        if resolved_port is None:
            if not resolved_container_name:
                raise ValueError("Either port or container_name is required for map_domain.")
            resolved_port = _get_existing_container_port(ssh, docker_command, resolved_container_name)
            if resolved_port is None:
                raise ValueError(f"Could not determine the published port for container '{resolved_container_name}'.")

        # Install nginx (and certbot if HTTPS enabled), write site config, reload
        _install_reverse_proxy_dependencies(ssh, enable_https=enable_https)
        site_name = _trim_name(f"mcp-domain-{_slugify(normalized_domain)}")
        nginx_config = _render_nginx_site(domain=normalized_domain, proxy_port=resolved_port)
        _write_nginx_site(ssh, site_name=site_name, nginx_config=nginx_config)
        _reload_nginx(ssh)
        _wait_for_local_proxy(ssh, domain=normalized_domain, proxy_port=resolved_port)
        steps.append({"step": "nginx_setup", "status": "ok", "site": site_name, "port": resolved_port})

        # ── STEP 4: TLS (certbot) — only when DNS is confirmed pointing to this server ──
        tls_enabled = False
        tls_error: str | None = None
        tls_email = (certbot_email or settings.deploy_certbot_email).strip()

        if not enable_https:
            steps.append({"step": "certbot", "status": "skipped", "detail": "enable_https=False"})
        elif not tls_email:
            steps.append({"step": "certbot", "status": "skipped", "detail": "certbot_email not configured"})
            dns_result.setdefault("warnings", []).append(
                "HTTPS was requested but certbot_email is not set — domain is running on HTTP only."
            )
        elif not dns_result.get("matches_target"):
            # DNS not yet pointing to our server — skip certbot to avoid burning Let's Encrypt rate limit
            msg = (
                f"Certbot skipped: DNS for {normalized_domain} still resolves to "
                f"{dns_result.get('resolved_ips')} instead of {resolved_dns_target_ip}. "
                "Re-run map_domain once DNS has propagated to get HTTPS automatically."
            )
            steps.append({"step": "certbot", "status": "skipped", "detail": msg})
            dns_result.setdefault("warnings", []).append(msg)
        else:
            try:
                _obtain_tls_certificate(ssh, domain=normalized_domain, email=tls_email)
                tls_enabled = True
                _wait_for_public_proxy(ssh, domain=normalized_domain, docs_path=normalized_docs_path, https=True)
                steps.append({"step": "certbot", "status": "ok"})
            except Exception as exc:
                tls_error = str(exc)
                steps.append({"step": "certbot", "status": "error", "detail": tls_error})
                dns_result.setdefault("warnings", []).append(
                    f"TLS certificate issuance failed: {tls_error}. "
                    "Ensure the domain DNS is propagated and port 80 is open on the server, then re-run map_domain."
                )

        if not tls_enabled:
            try:
                _wait_for_public_proxy(ssh, domain=normalized_domain, docs_path=normalized_docs_path, https=False)
                steps.append({"step": "http_check", "status": "ok"})
            except Exception as exc:
                steps.append({"step": "http_check", "status": "warning", "detail": str(exc)})

        scheme = "https" if tls_enabled else "http"
        public_url = f"{scheme}://{normalized_domain}"
        return {
            "mapped": True,
            "domain": normalized_domain,
            "public_url": public_url,
            "docs_url": f"{public_url}{normalized_docs_path}",
            "container_name": resolved_container_name,
            "port": resolved_port,
            "tls_enabled": tls_enabled,
            "tls_error": tls_error,
            "dns": dns_result,
            "hostinger": hostinger_result,
            "nginx_site": site_name,
            "steps": steps,
        }
    finally:
        ssh.close()


def _sanitize_github_token(raw_token: Any) -> str:
    token = str(raw_token or "").strip()
    if len(token) >= 2 and ((token[0] == '"' and token[-1] == '"') or (token[0] == "'" and token[-1] == "'")):
        token = token[1:-1].strip()
    return token


def _normalize_github_repo_url(repo_url: str) -> str:
    normalized = repo_url.strip()
    if not normalized:
        raise ValueError("github_repo_url is required.")
    if normalized.startswith("https://github.com/"):
        return normalized.removesuffix(".git")

    shorthand = normalized.strip("/")
    parts = [part for part in shorthand.split("/") if part]
    if len(parts) == 2:
        return f"https://github.com/{parts[0]}/{parts[1].removesuffix('.git')}"

    raise ValueError(
        "github_repo_url must be a valid GitHub repo URL like https://github.com/<owner>/<repo> or <owner>/<repo>."
    )


def _parse_github_repo(repo_url: str) -> tuple[str, str]:
    parsed = urlparse(repo_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError(
            "github_repo_url must be a valid GitHub repo URL like https://github.com/<owner>/<repo> or <owner>/<repo>."
        )

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise ValueError("github_repo_url must include owner and repository name.")
    return parts[0], parts[1].removesuffix(".git")


def _normalize_domain(domain: str) -> str:
    normalized = domain.strip().lower()
    if not normalized:
        raise ValueError("domain is required.")
    if "://" in normalized:
        parsed = urlparse(normalized)
        normalized = parsed.netloc or parsed.path
    normalized = normalized.strip("/").strip(".")
    if not normalized:
        raise ValueError("domain is required.")
    if "/" in normalized:
        raise ValueError("domain must not contain a path.")
    return normalized


def _normalize_docs_path(docs_path: str) -> str:
    value = (docs_path or "/docs").strip()
    if not value.startswith("/"):
        value = f"/{value}"
    return value.rstrip("/") or "/"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "fastapi-app"


def _trim_name(value: str, max_length: int = 63) -> str:
    trimmed = value[:max_length].rstrip("-")
    return trimmed or value[:max_length]


def _normalize_shell_command(command: str) -> str:
    parts = shlex.split(command.strip() or "docker")
    return " ".join(shlex.quote(part) for part in parts)


def _install_reverse_proxy_dependencies(ssh: paramiko.SSHClient, *, enable_https: bool) -> None:
    packages = ["nginx"]
    if enable_https:
        packages.extend(["certbot", "python3-certbot-nginx"])
    package_list = " ".join(packages)
    binaries = ["nginx"]
    if enable_https:
        binaries.append("certbot")
    binary_checks = "\n".join(
        f"if ! command -v {shlex.quote(binary)} >/dev/null 2>&1; then missing=1; fi" for binary in binaries
    )
    script = f"""
set -euo pipefail
missing=0
{binary_checks}
if [ "$missing" -eq 1 ]; then
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {package_list}
fi
sudo mkdir -p /var/www/certbot
"""
    _run_remote(ssh, script)


def _render_nginx_site(*, domain: str, proxy_port: int) -> str:
    return "\n".join(
        [
            "server {",
            "    listen 80;",
            "    listen [::]:80;",
            f"    server_name {domain};",
            "",
            "    client_max_body_size 25m;",
            "",
            "    location /.well-known/acme-challenge/ {",
            "        root /var/www/certbot;",
            "    }",
            "",
            "    location / {",
            f"        proxy_pass http://127.0.0.1:{proxy_port};",
            "        proxy_http_version 1.1;",
            "        proxy_set_header Host $host;",
            "        proxy_set_header X-Real-IP $remote_addr;",
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "        proxy_set_header X-Forwarded-Proto $scheme;",
            "        proxy_set_header Upgrade $http_upgrade;",
            "        proxy_set_header Connection \"upgrade\";",
            "        proxy_read_timeout 120s;",
            "    }",
            "}",
            "",
        ]
    )


def _write_nginx_site(ssh: paramiko.SSHClient, *, site_name: str, nginx_config: str) -> None:
    encoded_config = base64.b64encode(nginx_config.encode("utf-8")).decode("ascii")
    script = f"""
set -euo pipefail
tmp_file=/tmp/{site_name}.conf
printf '%s' {shlex.quote(encoded_config)} | base64 -d > "$tmp_file"
sudo mv "$tmp_file" /etc/nginx/sites-available/{site_name}
sudo ln -sfn /etc/nginx/sites-available/{site_name} /etc/nginx/sites-enabled/{site_name}
sudo rm -f /etc/nginx/sites-enabled/default
"""
    _run_remote(ssh, script)


def _reload_nginx(ssh: paramiko.SSHClient) -> None:
    _run_remote(ssh, "sudo nginx -t && sudo systemctl reload nginx")


def _wait_for_local_proxy(ssh: paramiko.SSHClient, *, domain: str, proxy_port: int) -> None:
    script = f"""
python3 - <<'PY'
import time
import urllib.request

url = 'http://127.0.0.1/'
headers = {{'Host': '{domain}'}}
for _ in range(20):
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=3) as response:
            if response.status < 500:
                raise SystemExit(0)
    except Exception:
        time.sleep(2)
raise SystemExit(1)
PY
"""
    exit_code, _, error_text = _run_remote(ssh, script, check=False)
    if exit_code != 0:
        raise RuntimeError(error_text or f"Nginx did not proxy traffic to port {proxy_port} in time.")


def _obtain_tls_certificate(ssh: paramiko.SSHClient, *, domain: str, email: str) -> None:
    script = f"""
set -euo pipefail
sudo certbot --nginx --non-interactive --agree-tos --redirect -m {shlex.quote(email)} -d {shlex.quote(domain)}
"""
    _run_remote(ssh, script)


def _wait_for_public_proxy(ssh: paramiko.SSHClient, *, domain: str, docs_path: str, https: bool) -> None:
    scheme = "https" if https else "http"
    port = 443 if https else 80
    insecure_flag = "-k" if https else ""
    script = f"""
set -euo pipefail
for _ in $(seq 1 20); do
  if curl -fsS {insecure_flag} --resolve {shlex.quote(domain)}:{port}:127.0.0.1 {shlex.quote(f'{scheme}://{domain}{docs_path}')} >/dev/null 2>&1; then
    exit 0
  fi
  sleep 2
done
exit 1
"""
    exit_code, _, error_text = _run_remote(ssh, script, check=False)
    if exit_code != 0:
        raise RuntimeError(error_text or f"{scheme.upper()} endpoint for {domain} did not become reachable in time.")


def _wait_for_dns_propagation(
    domain: str,
    target_ip: str,
    *,
    max_wait_seconds: int = 180,
    poll_interval: int = 10,
) -> dict[str, Any]:
    """
    Poll DNS until the domain resolves to target_ip or max_wait_seconds elapses.
    Returns the same shape as _check_dns_alignment so callers can use either.
    Non-blocking path: if already correct on first check, returns immediately.
    """
    import time

    deadline = time.monotonic() + max_wait_seconds
    attempts = 0
    last_resolved: list[str] = []

    while True:
        attempts += 1
        try:
            last_resolved = sorted(set(socket.gethostbyname_ex(domain)[2]))
        except OSError:
            last_resolved = []

        matches = target_ip in last_resolved
        if matches:
            return {
                "checked": True,
                "resolved_ips": last_resolved,
                "target_ip": target_ip,
                "matches_target": True,
                "propagation_attempts": attempts,
                "warnings": [],
            }

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        time.sleep(min(poll_interval, remaining))

    warnings = [
        f"DNS for {domain} resolves to {last_resolved or '(unresolvable)'} after {attempts} attempts "
        f"({max_wait_seconds}s wait) — expected {target_ip}. "
        "Certbot SSL challenge will be skipped until DNS propagates. "
        "Re-run map_domain after DNS update takes effect to enable HTTPS automatically."
    ]
    return {
        "checked": True,
        "resolved_ips": last_resolved,
        "target_ip": target_ip,
        "matches_target": False,
        "propagation_attempts": attempts,
        "warnings": warnings,
    }


def _check_dns_alignment(domain: str, target_ip: str) -> dict[str, Any]:
    try:
        resolved_ips = sorted(set(socket.gethostbyname_ex(domain)[2]))
    except OSError:
        resolved_ips = []
    matches = target_ip in resolved_ips
    warnings: list[str] = []
    if not matches:
        warnings.append(
            f"DNS for {domain} does not currently resolve to {target_ip}. Update your Hostinger A record if HTTPS validation fails."
        )
    return {
        "checked": True,
        "resolved_ips": resolved_ips,
        "target_ip": target_ip,
        "matches_target": matches,
        "warnings": warnings,
    }


def _hostinger_headers(api_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _relative_record_name(domain: str, zone_domain: str) -> str:
    if domain == zone_domain:
        return "@"
    suffix = f".{zone_domain}"
    if not domain.endswith(suffix):
        raise ValueError("domain must match hostinger_zone_domain or be a subdomain of it.")
    return domain[: -len(suffix)]


def _build_hostinger_dns_request(
    *,
    domain: str,
    zone_domain: str,
    target_ip: str,
    include_www_alias: bool,
) -> dict[str, Any]:
    record_name = _relative_record_name(domain, zone_domain)
    zone = [
        {
            "name": record_name,
            "records": [{"content": target_ip}],
            "ttl": 300,
            "type": "A",
        }
    ]
    if include_www_alias and record_name == "@":
        zone.append(
            {
                "name": "www",
                "records": [{"content": domain}],
                "ttl": 300,
                "type": "CNAME",
            }
        )
    return {"overwrite": False, "zone": zone}


def _sync_hostinger_dns(
    *,
    domain: str,
    zone_domain: str,
    target_ip: str,
    api_token: str,
    include_www_alias: bool,
) -> dict[str, Any]:
    settings = get_settings()
    payload = _build_hostinger_dns_request(
        domain=domain,
        zone_domain=zone_domain,
        target_ip=target_ip,
        include_www_alias=include_www_alias,
    )
    base_url = settings.hostinger_api_base_url.rstrip("/")
    headers = _hostinger_headers(api_token)

    with httpx.Client(timeout=30.0, headers=headers) as client:
        # First validate the zone exists and is accessible
        check_response = client.get(f"{base_url}/api/dns/v1/zones/{zone_domain}")
        if check_response.status_code == 404:
            return {
                "checked": True,
                "updated": False,
                "zone_domain": zone_domain,
                "skipped_reason": (
                    f"Zone '{zone_domain}' not found in Hostinger (HTTP 404). "
                    "Ensure hostinger_zone_domain exactly matches your domain in hPanel "
                    "(e.g. 'anervera.live' not 'anervea.ai') and the API token belongs to the same account."
                ),
            }
        if check_response.status_code == 401:
            return {
                "checked": False,
                "updated": False,
                "zone_domain": zone_domain,
                "skipped_reason": (
                    "Hostinger API token is invalid or expired (HTTP 401). "
                    "Regenerate a token from hPanel → API Access with DNS/zone permissions."
                ),
            }
        if check_response.status_code not in (200, 201):
            return {
                "checked": False,
                "updated": False,
                "zone_domain": zone_domain,
                "skipped_reason": (
                    f"Hostinger zone check failed: HTTP {check_response.status_code} — {check_response.text[:500]}"
                ),
            }

        # Zone exists — validate payload then apply update
        validate_response = client.post(f"{base_url}/api/dns/v1/zones/{zone_domain}/validate", json=payload)
        if validate_response.status_code not in (200, 201):
            return {
                "checked": True,
                "updated": False,
                "zone_domain": zone_domain,
                "skipped_reason": (
                    f"Hostinger DNS validation rejected payload: HTTP {validate_response.status_code} "
                    f"— {validate_response.text[:500]}"
                ),
            }

        update_response = client.put(f"{base_url}/api/dns/v1/zones/{zone_domain}", json=payload)
        if update_response.status_code not in (200, 201):
            raise RuntimeError(
                f"Hostinger DNS update failed: {update_response.status_code} {update_response.text[:1000]}"
            )

    return {
        "checked": True,
        "updated": True,
        "zone_domain": zone_domain,
        "payload": payload,
        "skipped_reason": None,
    }


def _connect_ssh(
    *,
    host: str,
    port: int,
    username: str,
    key_path: str,
    private_key: str,
) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    resolved_key_path = _resolve_ssh_key_path(key_path)
    if resolved_key_path:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            key_filename=resolved_key_path,
            look_for_keys=False,
            allow_agent=False,
            timeout=20,
        )
        return client

    pkey = _load_private_key(private_key)
    if pkey is None:
        raise ValueError(
            "SSH key is not configured. Set DEPLOY_SSH_KEY_PATH or DEPLOY_SSH_PRIVATE_KEY in the backend runtime "
            "environment (not only in .env.example), or mount mcp_automation.pem into the app."
        )

    client.connect(
        hostname=host,
        port=port,
        username=username,
        pkey=pkey,
        look_for_keys=False,
        allow_agent=False,
        timeout=20,
    )
    return client


def _resolve_ssh_key_path(configured_path: str) -> str:
    candidates: list[Path] = []
    if configured_path.strip():
        candidate = Path(configured_path.strip())
        candidates.append(candidate if candidate.is_absolute() else (BASE_DIR / candidate))
    candidates.append(BASE_DIR / "mcp_automation.pem")
    candidates.append(BASE_DIR / "mcp_automation.txt")

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def _load_private_key(private_key: str) -> paramiko.PKey | None:
    key_text = private_key.strip().replace("\\n", "\n")
    if not key_text:
        return None

    key_classes = tuple(
        key_class
        for key_class in (
            getattr(paramiko, "RSAKey", None),
            getattr(paramiko, "Ed25519Key", None),
            getattr(paramiko, "ECDSAKey", None),
            getattr(paramiko, "DSSKey", None),
        )
        if key_class is not None
    )
    for key_class in key_classes:
        try:
            return key_class.from_private_key(io.StringIO(key_text))
        except paramiko.SSHException:
            continue
    raise ValueError("DEPLOY_SSH_PRIVATE_KEY could not be parsed as a supported private key.")


def _run_remote(ssh: paramiko.SSHClient, script: str, *, check: bool = True) -> tuple[int, str, str]:
    command = f"bash -lc {shlex.quote(script)}"
    _, stdout, stderr = ssh.exec_command(command, timeout=900)
    exit_code = stdout.channel.recv_exit_status()
    out_text = stdout.read().decode("utf-8", errors="replace").strip()
    err_text = stderr.read().decode("utf-8", errors="replace").strip()
    if check and exit_code != 0:
        detail = err_text or out_text or f"remote command failed with exit code {exit_code}"
        raise RuntimeError(detail)
    return exit_code, out_text, err_text


def _sync_repo_on_remote(
    *,
    ssh: paramiko.SSHClient,
    repo_url: str,
    branch: str,
    remote_project_dir: str,
    github_token: str,
) -> None:
    remote_dir = PurePosixPath(remote_project_dir)
    base_dir = remote_dir.parent.as_posix()
    auth_exports, auth_unset = _git_auth_snippets(_sanitize_github_token(github_token))
    script = f"""
set -euo pipefail
REPO_URL={shlex.quote(repo_url)}
BRANCH={shlex.quote(branch)}
BASE_DIR={shlex.quote(base_dir)}
REPO_DIR={shlex.quote(remote_project_dir)}
mkdir -p "$BASE_DIR"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
  {auth_exports}
  git -C "$REPO_DIR" fetch --depth 1 origin "$BRANCH"
  git -C "$REPO_DIR" checkout -B "$BRANCH" "origin/$BRANCH"
  git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
  {auth_unset}
else
  rm -rf "$REPO_DIR"
  {auth_exports}
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
  {auth_unset}
fi
git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
"""
    _run_remote(ssh, script)


def _git_auth_snippets(token: str) -> tuple[str, str]:
    if not token:
        return ":", ":"

    basic_auth = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
    auth_header = f"AUTHORIZATION: basic {basic_auth}"
    exports = "\n".join(
        [
            "export GIT_CONFIG_COUNT=1",
            "export GIT_CONFIG_KEY_0=http.https://github.com/.extraheader",
            f"export GIT_CONFIG_VALUE_0={shlex.quote(auth_header)}",
        ]
    )
    unsets = "unset GIT_CONFIG_COUNT GIT_CONFIG_KEY_0 GIT_CONFIG_VALUE_0"
    return exports, unsets


def _remote_exists(sftp: paramiko.SFTPClient, path: str) -> bool:
    try:
        sftp.stat(path)
        return True
    except OSError:
        return False


def _detect_fastapi_module(sftp: paramiko.SFTPClient, remote_project_dir: str) -> str:
    for rel_path, module in COMMON_FASTAPI_CANDIDATES:
        file_path = str(PurePosixPath(remote_project_dir) / rel_path)
        if not _remote_exists(sftp, file_path):
            continue
        text = _read_remote_text(sftp, file_path)
        if _looks_like_fastapi_app(text):
            return module

    for file_path in _iter_remote_python_files(sftp, remote_project_dir):
        text = _read_remote_text(sftp, file_path)
        if not _looks_like_fastapi_app(text):
            continue
        relative = PurePosixPath(file_path).relative_to(PurePosixPath(remote_project_dir))
        return f"{'.'.join(relative.with_suffix('').parts)}:app"

    raise ValueError(
        "Could not detect a FastAPI app in the repository. Add a file such as backend/main.py or pass fastapi_module explicitly."
    )


def _looks_like_fastapi_app(text: str) -> bool:
    return bool(re.search(r"\bapp\s*(?::[^=]+)?=\s*FastAPI\s*\(", text))


def _iter_remote_python_files(sftp: paramiko.SFTPClient, remote_root: str) -> list[str]:
    root = PurePosixPath(remote_root)
    pending = [root]
    results: list[str] = []
    while pending:
        current = pending.pop()
        for entry in sftp.listdir_attr(current.as_posix()):
            name = entry.filename
            child = current / name
            if stat.S_ISDIR(entry.st_mode):
                if name in SKIP_DIRS:
                    continue
                pending.append(child)
                continue
            if name.endswith(".py"):
                results.append(child.as_posix())
    return results


def _detect_requirements_file(sftp: paramiko.SFTPClient, remote_project_dir: str) -> str | None:
    for rel_path in COMMON_REQUIREMENTS_FILES:
        file_path = str(PurePosixPath(remote_project_dir) / rel_path)
        if _remote_exists(sftp, file_path):
            return rel_path
    return None


def _detect_frontend_project(sftp: paramiko.SFTPClient, remote_project_dir: str) -> dict[str, str] | None:
    for rel_path in COMMON_FRONTEND_PACKAGE_CANDIDATES:
        file_path = str(PurePosixPath(remote_project_dir) / rel_path)
        if not _remote_exists(sftp, file_path):
            continue
        try:
            package = json.loads(_read_remote_text(sftp, file_path))
        except json.JSONDecodeError:
            continue
        if not _looks_like_frontend_package(package, rel_path=rel_path):
            continue
        package_dir = str(PurePosixPath(rel_path).parent)
        return {"package_dir": "." if package_dir in {"", "."} else package_dir}
    return None


def _looks_like_frontend_package(package: Any, *, rel_path: str) -> bool:
    if not isinstance(package, dict):
        return False
    scripts = package.get("scripts")
    if not isinstance(scripts, dict) or not str(scripts.get("build") or "").strip():
        return False
    if rel_path != "package.json":
        return True

    dependencies: set[str] = set()
    for key in ("dependencies", "devDependencies"):
        raw = package.get(key)
        if not isinstance(raw, dict):
            continue
        dependencies.update(str(name).strip() for name in raw.keys())
    frontend_markers = {
        "@vitejs/plugin-react",
        "next",
        "react",
        "react-dom",
        "svelte",
        "vite",
        "vue",
    }
    return any(marker in dependencies for marker in frontend_markers)


def _read_remote_text(sftp: paramiko.SFTPClient, path: str) -> str:
    with sftp.open(path, "rb") as handle:
        return handle.read().decode("utf-8", errors="replace")


def _render_dockerfile(
    *,
    fastapi_module: str,
    requirements_file: str | None,
    frontend_package_dir: str | None = None,
) -> str:
    install_line = (
        f"RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r {requirements_file}"
        if requirements_file
        else "RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir fastapi uvicorn[standard]"
    )
    lines: list[str] = []
    if frontend_package_dir:
        frontend_prefix = "" if frontend_package_dir in {"", "."} else f"{frontend_package_dir}/"
        frontend_source = "." if frontend_package_dir in {"", "."} else f"{frontend_package_dir}/"
        lines.extend(
            [
                "FROM node:20-slim AS frontend-builder",
                "",
                "WORKDIR /frontend",
                "",
                f"COPY {frontend_prefix}package*.json /frontend/",
                "RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi",
                f"COPY {frontend_source} /frontend/",
                (
                    "RUN npm run build && rm -rf /frontend-out && "
                    "if [ -d dist ]; then cp -R dist /frontend-out; "
                    "elif [ -d build ]; then cp -R build /frontend-out; "
                    "else echo 'Frontend build output not found (expected dist or build)' >&2; exit 1; fi"
                ),
                "",
            ]
        )
    lines.extend(
        [
            "FROM python:3.12-slim",
            "",
            "WORKDIR /app",
            "",
            "ENV PYTHONDONTWRITEBYTECODE=1",
            "ENV PYTHONUNBUFFERED=1",
            "",
            "COPY . /app",
        ]
    )
    if frontend_package_dir:
        lines.append("COPY --from=frontend-builder /frontend-out /app/.mcp-frontend")
    lines.extend(
        [
            install_line,
            "",
            "EXPOSE 8000",
            f'CMD ["uvicorn", "{fastapi_module}", "--host", "0.0.0.0", "--port", "8000"]',
            "",
        ]
    )
    return "\n".join(lines)


def _render_frontend_wrapper(*, fastapi_module: str) -> str:
    module_name, app_name = fastapi_module.split(":", 1)
    return "\n".join(
        [
            "from importlib import import_module",
            "from pathlib import Path",
            "",
            "from fastapi import HTTPException",
            "from fastapi.responses import FileResponse",
            "",
            f'MODULE_NAME = "{module_name}"',
            f'APP_NAME = "{app_name}"',
            "FRONTEND_DIR = Path(__file__).resolve().parent / '.mcp-frontend'",
            "API_PREFIXES = {",
            "    'auth',",
            "    'chat',",
            "    'docs',",
            "    'health',",
            "    'internal',",
            "    'mcp',",
            "    'memory',",
            "    'openapi.json',",
            "    'redoc',",
            "    'tool',",
            "    'tools',",
            "}",
            "",
            "module = import_module(MODULE_NAME)",
            "app = getattr(module, APP_NAME)",
            "",
            "@app.get('/', include_in_schema=False)",
            "async def mcp_frontend_root():",
            "    index_file = FRONTEND_DIR / 'index.html'",
            "    if not index_file.exists():",
            "        raise HTTPException(status_code=404, detail='Frontend build missing from deployment image.')",
            "    return FileResponse(index_file)",
            "",
            "@app.get('/{full_path:path}', include_in_schema=False)",
            "async def mcp_frontend_spa(full_path: str):",
            "    first_segment = full_path.split('/', 1)[0]",
            "    if first_segment in API_PREFIXES:",
            "        raise HTTPException(status_code=404, detail='Not found')",
            "    candidate = (FRONTEND_DIR / full_path).resolve()",
            "    if candidate.is_file() and candidate.is_relative_to(FRONTEND_DIR):",
            "        return FileResponse(candidate)",
            "    index_file = FRONTEND_DIR / 'index.html'",
            "    if not index_file.exists():",
            "        raise HTTPException(status_code=404, detail='Frontend build missing from deployment image.')",
            "    return FileResponse(index_file)",
            "",
        ]
    )


def _ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    current = PurePosixPath(remote_dir)
    parts = current.parts
    prefix = PurePosixPath(parts[0]) if parts and parts[0] == "/" else PurePosixPath(".")
    for part in parts[1:] if prefix.as_posix() == "/" else parts:
        prefix = prefix / part
        try:
            sftp.stat(prefix.as_posix())
        except OSError:
            sftp.mkdir(prefix.as_posix())


def _write_remote_text(sftp: paramiko.SFTPClient, path: str, content: str) -> None:
    _ensure_remote_dir(sftp, str(PurePosixPath(path).parent))
    with sftp.open(path, "wb") as handle:
        handle.write(content.encode("utf-8"))


def _get_existing_container_port(ssh: paramiko.SSHClient, docker_command: str, container_name: str) -> int | None:
    script = f"""
set -e
{docker_command} inspect -f '{{{{(index (index .NetworkSettings.Ports "8000/tcp") 0).HostPort}}}}' {shlex.quote(container_name)}
"""
    exit_code, stdout, _ = _run_remote(ssh, script, check=False)
    if exit_code != 0 or not stdout.strip():
        return None
    try:
        return int(stdout.strip())
    except ValueError:
        return None


def _find_open_remote_port(ssh: paramiko.SSHClient, *, start: int, end: int) -> int:
    script = f"""
python3 - <<'PY'
import socket

for port in range({start}, {end} + 1):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            continue
        print(port)
        raise SystemExit(0)
raise SystemExit(1)
PY
"""
    _, stdout, _ = _run_remote(ssh, script)
    try:
        return int(stdout.strip())
    except ValueError as exc:
        raise RuntimeError("Could not allocate a free remote port for deployment.") from exc


def _build_and_run_container(
    *,
    ssh: paramiko.SSHClient,
    docker_command: str,
    remote_project_dir: str,
    dockerfile_path: str,
    image_name: str,
    container_name: str,
    host_port: int,
) -> None:
    script = f"""
set -euo pipefail
{docker_command} build -t {shlex.quote(image_name)} -f {shlex.quote(dockerfile_path)} {shlex.quote(remote_project_dir)}
{docker_command} rm -f {shlex.quote(container_name)} >/dev/null 2>&1 || true
{docker_command} run -d --name {shlex.quote(container_name)} --restart unless-stopped -p {host_port}:8000 {shlex.quote(image_name)}
"""
    _run_remote(ssh, script)


def _wait_for_fastapi(
    *,
    ssh: paramiko.SSHClient,
    docker_command: str,
    container_name: str,
    host_port: int,
) -> None:
    script = f"""
python3 - <<'PY'
import time
import urllib.request

url = "http://127.0.0.1:{host_port}/docs"
for _ in range(30):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            if response.status < 500:
                raise SystemExit(0)
    except Exception:
        time.sleep(2)
raise SystemExit(1)
PY
"""
    exit_code, _, error_text = _run_remote(ssh, script, check=False)
    if exit_code == 0:
        return

    _, _, logs = _run_remote(
        ssh,
        f"{docker_command} logs --tail 80 {shlex.quote(container_name)}",
        check=False,
    )
    detail = logs or error_text or "FastAPI container did not become healthy in time."
    raise RuntimeError(detail)
