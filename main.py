from fastapi import FastAPI
import uvicorn
from api.routers import users, splitbills, auth

app = FastAPI(
    title="SplitBill API",
    description="Manage split bills, expenses, and members",
    version="1.0.0",
)

# Include routers
app.include_router(splitbills.router, tags=["splitbills"])
app.include_router(users.router, tags=["users"])
app.include_router(auth.router, tags=["auth"])

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
