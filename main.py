import uvicorn
from config.settings import API_HOST, API_PORT, API_DEBUG

if __name__ == "__main__":
    uvicorn.run(
        "api.server:app",
        host=API_HOST,
        port=API_PORT,
        reload=API_DEBUG,
    )
