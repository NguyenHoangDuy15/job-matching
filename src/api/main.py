from fastapi import FastAPI

app = FastAPI(title="Job Matching API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
