from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Note, User
from ..schemas import DeployInDockerRequest, MapDomainRequest, NoteCreateRequest, UserOut
from ..services.local_mcp_service import load_messages, run_local_mcp_tool

router = APIRouter(prefix="/internal", tags=["internal"])
settings = get_settings()


def verify_mcp_key(x_mcp_api_key: str = Header(default="")) -> None:
    if x_mcp_api_key != settings.mcp_api_key:
        raise HTTPException(status_code=401, detail="Invalid MCP API key")


@router.get("/users/{user_id}", response_model=UserOut, dependencies=[Depends(verify_mcp_key)])
def internal_get_user(user_id: int, db: Session = Depends(get_db)) -> UserOut:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/notes", dependencies=[Depends(verify_mcp_key)])
def internal_save_note(payload: NoteCreateRequest, db: Session = Depends(get_db)):
    note = Note(user_id=payload.user_id, title=payload.title, content=payload.content)
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"id": note.id, "title": note.title, "content": note.content}


@router.get("/notes/search", dependencies=[Depends(verify_mcp_key)])
def internal_search_notes(user_id: int, query: str, db: Session = Depends(get_db)):
    notes = (
        db.query(Note)
        .filter(
            Note.user_id == user_id,
            or_(Note.title.ilike(f"%{query}%"), Note.content.ilike(f"%{query}%")),
        )
        .all()
    )
    return {
        "results": [{"id": n.id, "title": n.title, "content": n.content} for n in notes],
        "count": len(notes),
    }


@router.get("/messages/export", dependencies=[Depends(verify_mcp_key)])
def internal_export_messages(download: bool = False):
    messages = load_messages()
    payload = {"count": len(messages), "messages": messages}
    if not download:
        return payload

    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="messages-export.json"'},
    )


@router.post("/deployments", dependencies=[Depends(verify_mcp_key)])
def internal_deploy_in_docker(payload: DeployInDockerRequest):
    try:
        result = run_local_mcp_tool(
            "deploy_inDocker",
            payload.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Unexpected non-dict response from deploy_inDocker")
    return result


@router.post("/domain-mappings", dependencies=[Depends(verify_mcp_key)])
def internal_map_domain(payload: MapDomainRequest):
    try:
        result = run_local_mcp_tool(
            "map_domain",
            payload.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Unexpected non-dict response from map_domain")
    return result
