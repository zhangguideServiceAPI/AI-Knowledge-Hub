from fastapi import FastAPI

app = FastAPI(title="AI Knowledge Hub")


@app.get("/health")
def health_check():
    return {"status": "ok"}
