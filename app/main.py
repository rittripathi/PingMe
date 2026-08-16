from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware 
from app.routers import auth_routes, trigger_routes, user_routes, internal_routes
from app.database import Base, engine


Base.metadata.create_all(bind=engine)
app = FastAPI(
    title="PingMe",
    description="A unified alert platform -- ping me when X happens.",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(user_routes.router)
app.include_router(trigger_routes.router)
app.include_router(internal_routes.router)


@app.get("/health")
def health_check():
    """Simple endpoint to confirm the server is up and responding."""
    return {"status": "ok"}


