import uvicorn


def main() -> None:
    uvicorn.run("backend.app:app")
