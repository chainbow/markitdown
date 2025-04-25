import sys
import logging
from typing import Any
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.routing import Mount, Route
from mcp.server import Server
from markitdown import MarkItDown
from starlette.responses import JSONResponse
import uvicorn

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server for MarkItDown (SSE)
mcp = FastMCP("markitdown")


@mcp.tool()
async def convert_to_markdown(uri: str) -> str:
    """Convert a resource described by an http:, https:, file: or data: URI to markdown"""
    return MarkItDown().convert_uri(uri).markdown


def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    async def handle_http_convert(request: Request) -> JSONResponse:
        try:
            # 获取请求体中的URI参数
            body = await request.json()
            uri = body.get("uri")
            
            if not uri:
                return JSONResponse(
                    {"error": "Missing required parameter: uri"}, 
                    status_code=400
                )
            
            # 使用相同的转换函数
            markdown = await convert_to_markdown(uri)
            return JSONResponse({"markdown": markdown})
            
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            return JSONResponse(
                {"error": str(e)}, 
                status_code=500
            )

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
            Route("/convert", endpoint=handle_http_convert, methods=["POST"]),
        ],
    )


# Main entry point
def main():
    logger.info("Starting markitdown-mcp server")
    logger.debug(f"Command line arguments: {sys.argv}")
    
    import argparse

    mcp_server = mcp._mcp_server

    parser = argparse.ArgumentParser(description="Run MCP SSE-based MarkItDown server")

    parser.add_argument(
        "--sse",
        action="store_true",
        help="Run the server with SSE transport rather than STDIO (default: False)",
    )
    parser.add_argument(
        "--host", default=None, help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=None, help="Port to listen on (default: 3001)"
    )
    
    try:
        args = parser.parse_args()
        logger.debug(f"Parsed arguments: {args}")
    except Exception as e:
        logger.error(f"Error parsing arguments: {e}")
        raise

    if not args.sse and (args.host or args.port):
        error_msg = "Host and port arguments are only valid when using SSE transport."
        logger.error(error_msg)
        parser.error(error_msg)
        sys.exit(1)

    if args.sse:
        logger.info("Starting in SSE mode")
        starlette_app = create_starlette_app(mcp_server, debug=True)
        host = args.host if args.host else "127.0.0.1"
        port = args.port if args.port else 3001
        logger.info(f"Binding to {host}:{port}")
        uvicorn.run(
            starlette_app,
            host=host,
            port=port,
        )
    else:
        logger.info("Starting in STDIO mode")
        mcp.run()


if __name__ == "__main__":
    main()
