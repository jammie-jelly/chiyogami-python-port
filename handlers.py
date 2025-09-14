from fastapi import Request, Depends, Response, HTTPException
from fastapi.responses import ORJSONResponse
from db_sqlalchemy import database, pastes, users
from models_sql import UserCreate
from auth import require_session
from rate_limit import check_and_record_rate_limit, get_ip_address
from sqlalchemy import insert, select, and_, or_, delete
from datetime import datetime, timezone, timedelta
import os
import bcrypt
from jinja2 import Environment, select_autoescape
import sqlite3
import re
import json
import qrcode
import io

def to_iso_z(dt):
    """Convert a datetime to an RFC3339-like ISO string with trailing Z for UTC"""
    if not dt:
        return None
    try:
        return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except Exception:
        try:
            return datetime.fromisoformat(str(dt)).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        except Exception:
            return str(dt)

async def delete_expired_pastes():
    q = delete(pastes).where(pastes.c.expiration != None).where(pastes.c.expiration < datetime.now().astimezone())
    await database.execute(q)


async def optional_auth(request: Request):
    try:
        return await require_session(request)
    except HTTPException:
        return None  # treat as anonymous

def parse_go_duration(duration: str) -> timedelta:
    """
    Parses Go-style duration strings like '39h', '2h30m', '45m', '1.5h', '2s', etc.
    Mimics Go's time.ParseDuration.
    """
    pattern = re.compile(r'(\d+\.?\d*)(ns|us|µs|ms|s|m|h)')
    total_seconds = 0.0

    for match in pattern.finditer(duration):
        value, unit = match.groups()
        value = float(value)
        if unit == "ns":
            total_seconds += value / 1_000_000_000
        elif unit in ("us", "µs"):
            total_seconds += value / 1_000_000
        elif unit == "ms":
            total_seconds += value / 1000
        elif unit == "s":
            total_seconds += value
        elif unit == "m":
            total_seconds += value * 60
        elif unit == "h":
            total_seconds += value * 3600
    if total_seconds == 0:
        raise ValueError(f"Invalid duration: {duration}")
    return timedelta(seconds=total_seconds)


async def create_paste_handler(request: Request, auth=Depends(optional_auth)):
    # Rate limit using composite identifier: sessionIdentifier|ip
    ip = get_ip_address(request)
    session_identifier = "anon"
    user_id = None
    if isinstance(auth, dict) and auth.get("type") == "session":
        try:
            user_id = int(auth.get("user_id"))
            session_identifier = f"user-{user_id}"
        except Exception:
            session_identifier = "anon"
    identifier = f"{session_identifier}|{ip}"

    allowed = await check_and_record_rate_limit(request, identifier)
    if not allowed:
        return ORJSONResponse(status_code=429, content={"message": "Rate limit exceeded"})

    # --- Parse request body (raw file or JSON) ---
    max_char_content = int(os.getenv("MAX_CHAR_CONTENT") or 50000)
    max_bytes = max_char_content * 5
    body_bytes = bytearray()
    size = 0

    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            return ORJSONResponse(status_code=400, content={"message": f"Content invalid or size exceeds {max_char_content} max chars"})
        body_bytes.extend(chunk)

    content_type = request.headers.get("content-type", "")
    pasteRequest = {"content": "", "visibility": "", "expiration": "", "isEncrypted": False}

    if not content_type or content_type.startswith("text/"):
        pasteRequest["content"] = body_bytes.decode(errors="ignore")
    else:
        try:
            data = json.loads(body_bytes)
            pasteRequest.update(data)
        except Exception:
            return ORJSONResponse(status_code=400, content={"message": "Request body not compatible JSON format"})

    content = pasteRequest["content"].strip()
    if content == "" or len(content) > max_char_content:
        return ORJSONResponse(status_code=400, content={"message": f"Content invalid or size exceeds {max_char_content} max chars"})

    # Visibility
    visibility = pasteRequest.get("visibility") or "Public"
    if visibility not in ("Public", "Unlisted", "Private"):
        return ORJSONResponse(status_code=400, content={"message": "Invalid visibility"})

    # Expiration
    default_expiration = os.getenv("PASTE_DEFAULT_EXPIRATION") or "24h"
    expiration = pasteRequest.get("expiration") or default_expiration
    expiration_dt = None
    if expiration.lower() != "never":
        try:
            expiration_dt = datetime.now().astimezone() + parse_go_duration(expiration)
        except Exception:
            if expiration == default_expiration:
                return ORJSONResponse(status_code=500, content={"message": "PASTE_DEFAULT_EXPIRATION invalid"})
            return ORJSONResponse(status_code=400, content={"message": "Invalid expiration value"})

    # Title
    title = await generate_unique_title()

    # DB insert
    query = insert(pastes).values(
        title=title,
        content=content,
        visibility=visibility,
        created_at=datetime.now().astimezone(),
        expiration=expiration_dt,
        is_encrypted=pasteRequest.get("isEncrypted", False),
        user_id=user_id,
        is_user_paste=user_id is not None
    )
    paste_id = await database.execute(query)

    return {"title": title}

async def generate_unique_title():
    import random, string
    letters = string.ascii_letters
    while True:
        title = ''.join(random.choice(letters) for _ in range(4))
        # pass columns/tables directly to select()
        q = select(pastes.c.id).where(pastes.c.title == title)
        row = await database.fetch_one(q)
        if not row:
            return title

async def get_paste_handler(title: str, request: Request):
    # delete expired pastes
    await delete_expired_pastes()
    # select the table directly
    q = select(pastes).where(and_(pastes.c.title == title, or_(pastes.c.expiration == None, pastes.c.expiration > datetime.now(timezone.utc))))
    row = await database.fetch_one(q)
    if not row:
        return ORJSONResponse(status_code=404, content={"message": "Paste not found or has expired"})

    # Normalize database row to dict to avoid databases.Record attribute errors
    rr = dict(row)

    # Prepare paste data structure for HTML client
    accept = (request.headers.get("accept") or "").lower()
    created_at = rr.get("created_at")
    updated_at = rr.get("updated_at")
    expiration = rr.get("expiration")
    created_iso = to_iso_z(created_at)
    updated_iso = to_iso_z(updated_at)

    def time_until_expiration(expiry_dt):
        if expiry_dt is None:
            return "Never"
        if expiry_dt.tzinfo is None:
            expiry = expiry_dt.astimezone()
        else:
            expiry = expiry_dt

        now = datetime.now().astimezone()
        diff = expiry - now
        seconds = int(diff.total_seconds())
        if seconds <= 0:
            return ""

        units = [ (24*3600, 'day'), (3600, 'hour'), (60, 'minute'), (1, 'second') ]
        for sec, name in units:
            n = seconds // sec
            if n > 0:
                plural = '' if n == 1 else 's'
                return f"in {n} {name}{plural}"
        return ""

    expiration_str = time_until_expiration(expiration)

    if "text/html" in accept:
        tpl_path = os.path.join(os.getcwd(), 'public', 'tmpl.html')
        try:
            with open(tpl_path, 'r', encoding='utf-8') as f:
                tpl = f.read()
        except Exception:
            return ORJSONResponse(status_code=500, content={"message": "Failed to load template"})

        # Remove define wrapper start
        tpl = re.sub(r'{{\s*define\s+"[^"]+"\s*}}', '', tpl)
        # Remove only the final define end (the one closing the template definition)
        tpl = re.sub(r'{{\s*end\s*}}\s*$', '', tpl)

        # Convert if/else/end blocks: '{{ if .Var }}' -> '{% if Var %}', '{{ else }}' -> '{% else %}', remaining '{{ end }}' -> '{% endif %}'
        tpl = re.sub(r'{{\s*if\s*\.([A-Za-z0-9_]+)\s*}}', r'{% if \1 %}', tpl)
        tpl = re.sub(r'{{\s*else\s*}}', r'{% else %}', tpl)
        tpl = re.sub(r'{{\s*end\s*}}', r'{% endif %}', tpl)

        # Equivalent of {{.Content | html}}
        tpl = re.sub(r'{{\s*\.([A-Za-z0-9_]+)\s*(\|\s*html)?\s*}}', r'{{ \1 }}', tpl)

        # Convert plain placeholders like {{.Title}} -> {{ Title }}
        tpl = re.sub(r'{{\s*\.([A-Za-z0-9_]+)\s*}}', r'{{ \1 }}', tpl)

        # Create jinja environment and render
        env = Environment(autoescape=select_autoescape(['html', 'xml']))
        try:
            template = env.from_string(tpl)
            is_enc_bool = bool(rr.get('is_encrypted', False))
            # Render JS-friendly lowercase boolean literal
            is_enc_js = 'true' if is_enc_bool else 'false'
            rendered = template.render(
                Title=rr.get('title'),
                Content=rr.get('content'),
                CreatedAt=created_iso,
                Expiration=expiration_str,
                IsEncrypted=is_enc_js,
            )
        except Exception as e:
            return ORJSONResponse(status_code=500, content={"message": f"Template render error: {str(e)}"})

        return Response(content=rendered, media_type='text/html')

    # Otherwise return JSON with keys the client expects
    payload = {
        "ID": rr.get("id"),
        "Title": rr.get("title"),
        "Content": rr.get("content"),
        "CreatedAt": created_iso,
        "UpdatedAt": updated_iso,
        "Expiration": to_iso_z(expiration),
        "Visibility": rr.get("visibility"),
        "IsEncrypted": bool(rr.get("is_encrypted", False)),
        "UserID": rr.get("user_id"),
        "IsUserPaste": bool(rr.get("is_user_paste", False)),
    }
    return ORJSONResponse(content=payload)

async def list_pastes_handler(request: Request):
    await delete_expired_pastes()
    search = request.query_params.get("search")
    q = select(pastes).where(and_(pastes.c.visibility == "Public", pastes.c.is_encrypted == False))
    if search:
        pat = f"%{search}%"
        q = q.where(or_(pastes.c.title.like(pat), pastes.c.content.like(pat)))
    q = q.order_by(pastes.c.created_at.desc())
    rows = await database.fetch_all(q)

    result = []
    for r in rows:
        rr = dict(r)
        created = rr.get("created_at")
        updated = rr.get("updated_at")
        expiration = rr.get("expiration")

        result.append({
            "ID": rr.get("id"),
            "CreatedAt": to_iso_z(created),
            "UpdatedAt": to_iso_z(updated),
            "Title": rr.get("title"),
            "Content": rr.get("content"),
            "Visibility": rr.get("visibility"),
            "Expiration": to_iso_z(expiration),
            "IsEncrypted": bool(rr.get("is_encrypted", False)),
            "UserID": rr.get("user_id"),
            "IsUserPaste": bool(rr.get("is_user_paste", False)),
        })

    return ORJSONResponse(content=result)

async def list_user_pastes_handler(auth=Depends(require_session)):
    # require session user id
    if not isinstance(auth, dict) or auth.get("type") != "session":
        return ORJSONResponse(status_code=401, content={"message": "Unauthorized"})
    user_id = int(auth.get("user_id"))
    q = select(pastes).where(and_(pastes.c.user_id == user_id, pastes.c.is_user_paste == True))
    rows = await database.fetch_all(q)
    result = []
    for r in rows:
        rr = dict(r)
        created = rr.get("created_at")
        created_iso = to_iso_z(created)
        result.append({
            "Title": rr.get("title"),
            "Content": rr.get("content"),
            "CreatedAt": created_iso,
        })
    return ORJSONResponse(content=result)

async def register_handler(user: UserCreate, request: Request):
    identifier = f"register|{get_ip_address(request)}"
    allowed = await check_and_record_rate_limit(request, identifier)
    if not allowed:
        return ORJSONResponse(status_code=429, content={"message": "Rate limit exceeded"})

    if len(user.username) > 8:
        return ORJSONResponse(status_code=400, content={"message": "Username must be at most 8 characters"})
    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()
    q = insert(users).values(username=user.username, password=hashed)
    try:
        await database.execute(q)
    except sqlite3.IntegrityError as e:
        return ORJSONResponse(status_code=400, content={"message": str(e)})
    return {"message": "User registered"}

async def login_handler(loginData: dict, request: Request):
    identifier = f"login|{get_ip_address(request)}"
    allowed = await check_and_record_rate_limit(request, identifier)
    if not allowed:
        return ORJSONResponse(status_code=429, content={"message": "Rate limit exceeded"})
    q = select(users).where(users.c.username == loginData.get("username"))
    row = await database.fetch_one(q)
    if not row:
        return ORJSONResponse(status_code=401, content={"message": "Invalid credentials"})
    if not bcrypt.checkpw(loginData.get("password").encode(), row["password"].encode()):
        return ORJSONResponse(status_code=401, content={"message": "Bad password"})
    # set session cookie
    request.session["user_id"] = row["id"]
    return Response(status_code=200)

async def logout_handler(request: Request):
    # Clear session
    request.session["user_id"] = None
    return Response(status_code=200)

async def delete_account_handler(request: Request, auth=Depends(require_session)):
    identifier = f"delete-account|{get_ip_address(request)}"
    allowed = await check_and_record_rate_limit(request, identifier)
    if not allowed:
        return ORJSONResponse(status_code=429, content={"message": "Rate limit exceeded"})
    if not isinstance(auth, dict) or auth.get("type") != "session":
        return ORJSONResponse(status_code=401, content={"message": "Unauthorized"})
    user_id = int(auth.get("user_id"))
    q = delete(users).where(users.c.id == user_id)
    await database.execute(q)
    q2 = delete(pastes).where(pastes.c.user_id == user_id)
    await database.execute(q2)
    request.session["user_id"] = None
    return {"message": "account deleted"}

async def delete_paste_handler(title: str, auth=Depends(require_session), request: Request = None):
    if not isinstance(auth, dict) or auth.get("type") != "session":
        return ORJSONResponse(status_code=401, content={"message": "Unauthorized"})
    user_id = int(auth.get("user_id"))
    identifier = f"delete-pastes|{get_ip_address(request)}" if request is not None else f"delete-pastes|"
    allowed = await check_and_record_rate_limit(request, identifier)
    if not allowed:
        return ORJSONResponse(status_code=429, content={"message": "Rate limit exceeded"})
    q = select(pastes).where(pastes.c.title == title)
    row = await database.fetch_one(q)
    if not row:
        return ORJSONResponse(status_code=404, content={"message": "Paste not found"})
    if row["user_id"] != user_id:
        return ORJSONResponse(status_code=403, content={"message": "Forbidden"})
    q2 = delete(pastes).where(pastes.c.id == row["id"])
    await database.execute(q2)
    return {"message": "Paste deleted"}

async def generate_qr_handler(request: Request):
    if request.headers.get("X-Requested-By") != "qr-allowed":
        return ORJSONResponse(status_code=403, content={"message": "Forbidden"})
    url = request.query_params.get("url")
    if not url:
        return ORJSONResponse(status_code=400, content={"message": "Missing 'url'"})
    img = qrcode.make(url)
    img = img.resize((256, 256))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.read(), media_type="image/png")

async def health_handler():
    db_path = os.getenv("DATABASE_PATH")
    if not db_path:
        db_path = os.path.abspath(os.path.join(os.getcwd(), "pastes", "pastes.db"))
    if not os.path.exists(db_path):
        return ORJSONResponse(status_code=500, content={"message": {"status":"error","db_status":"missing_file"}})
    info = os.stat(db_path)
    if info.st_size < 100:
        return ORJSONResponse(status_code=500, content={"message": {"status":"error","db_status":"corrupted"}})
    return {"status":"ok","db_status":"ok"}

