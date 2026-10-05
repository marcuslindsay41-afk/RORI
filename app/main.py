from fastapi import FastAPI

from app.api.routes import router
from app.api.analysis import router as analysis_router
from app.api.pos import router as pos_router
from app.api.inventory import router as inventory_router
from app.api.labor import router as labor_router
from app.api.sync import router as sync_router
from app.api.auth import router as auth_router

app = FastAPI()
app.include_router(router)
app.include_router(analysis_router)
app.include_router(pos_router)
app.include_router(inventory_router)
app.include_router(labor_router)
app.include_router(sync_router)
app.include_router(auth_router)
