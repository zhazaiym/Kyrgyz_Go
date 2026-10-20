import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mysite.database import db as database
from mysite.api.chat_auth import router as chat_auth_router
from mysite.api.chat import chat_router
from mysite.api.chat_ws import router as chat_ws_router

from mysite.api.admin import admin_router

app = FastAPI(title="KYRGYZGO", description="KYRGYZGO Tourism API", version="1.0.0")

@asynccontextmanager
async def lifespan(app: FastAPI):
    database.Base.metadata.create_all(bind=database.engine)
    yield


app.router.lifespan_context = lifespan

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(admin_router)
app.include_router(chat_auth_router)
app.include_router(chat_router)
app.include_router(chat_ws_router)


@app.get("/")
def home():
    return {"message": "Welcome to KYRGYZGO API"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
