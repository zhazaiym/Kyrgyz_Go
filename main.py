import uvicorn

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mysite.database.db import Base, engine
import mysite.database.models

from mysite.api.admin import admin_router

app = FastAPI(
    title="KYRGYZGO",
    description="KYRGYZGO Tourism API",
    version="1.0.0"
)

Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(admin_router)


@app.get("/")
def home():
    return {"message": "Welcome to KYRGYZGO API"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )