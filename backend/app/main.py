from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ✅ import all routers you want to expose
from app.api import rules_summary, extract, upload_doc

app = FastAPI(title="Harmonization Dashboard API", version="1.0")

# ✅ register routers
app.include_router(rules_summary.router, prefix="/api")
app.include_router(extract.router, prefix="/api")
app.include_router(upload_doc.router, prefix="/api")

# ✅ CORS setup
origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Health check route
@app.get("/api/health")
def health():
    return {"status": "ok"}
