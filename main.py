from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
from api.routers import guest, users, splitbills, auth

app = FastAPI(
    title="SplitBill API",
    description="Manage split bills, expenses, and members",
    version="1.0.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(splitbills.router, tags=["splitbills"])
app.include_router(users.router, tags=["users"])
app.include_router(auth.router, tags=["auth"])
app.include_router(guest.router, tags=["guests"])


@app.get("/")
async def serve_spa():
    return FileResponse("index.html")


if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
