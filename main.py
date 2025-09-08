from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
from contextlib import asynccontextmanager
from starlette.middleware.sessions import SessionMiddleware
import secrets
import db_sqlalchemy
from handlers import (
    create_paste_handler, get_paste_handler, delete_paste_handler, list_pastes_handler,
    list_user_pastes_handler, register_handler, login_handler, logout_handler,
    delete_account_handler, generate_qr_handler, health_handler
)

# load env
load_dotenv()

# Session secret
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(32)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await db_sqlalchemy.init_db()
    await db_sqlalchemy.database.connect()
    yield
    # shutdown
    await db_sqlalchemy.database.disconnect()

# Create FastAPI app
app = FastAPI(title="Chiyogami FastAPI Port - Backend", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# CORS - allow all origins in dev, configure in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes mirroring Go service
app.post("/paste")(create_paste_handler)
app.put("/paste")(create_paste_handler)
app.get("/paste/{title}")(get_paste_handler)
app.delete("/paste/{title}")(delete_paste_handler)
app.get("/pastes")(list_pastes_handler)
app.get("/user/pastes")(list_user_pastes_handler)
app.post("/register")(register_handler)
app.post("/login")(login_handler)
app.post("/logout")(logout_handler)
app.delete("/delete-account")(delete_account_handler)
app.get("/generate-qr")(generate_qr_handler)
app.get("/health")(health_handler)

# Serve simple static pages similar to Go's public/ mapping
@app.get("/list", include_in_schema=False)
async def list_page():
    from fastapi.responses import FileResponse
    return FileResponse("./public/list.html")

@app.get("/about", include_in_schema=False)
async def about_page():
    from fastapi.responses import FileResponse
    return FileResponse("./public/about.html")

from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="public", html=True), name="public")
