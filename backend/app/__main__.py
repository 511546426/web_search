"""在 backend 目录执行: python -m app

默认监听 0.0.0.0，可通过服务器公网 IP 或域名访问。
环境变量: HOST（默认 0.0.0.0）、PORT（默认 8000）、UVICORN_RELOAD=1 开启热重载。
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        reload=os.environ.get("UVICORN_RELOAD", "").lower() in ("1", "true", "yes"),
    )
