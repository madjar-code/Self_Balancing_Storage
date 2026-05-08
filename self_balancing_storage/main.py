from __future__ import annotations
import asyncio
import uvicorn

from .api.app import create_app
from .config import Config
from .runtime import Runtime


async def main() -> None:
    config = Config()
    runtime = Runtime(config)
    await runtime.start()

    app = create_app(runtime)
    server_config = uvicorn.Config(app, host=config.api_host, port=config.api_port, log_level="info")
    server = uvicorn.Server(server_config)

    try:
        await server.serve()
    finally:
        await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
