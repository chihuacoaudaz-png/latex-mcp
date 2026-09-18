import os
import tempfile
import subprocess
import base64
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport

port = int(os.environ.get("PORT", 10000))
mcp = FastMCP("LatexCompilerService")

@mcp.tool()
def compilar_cv_latex(codigo_latex: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "cv.tex")
        pdf_path = os.path.join(tmpdir, "cv.pdf")
        
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(codigo_latex)
            
        resultado = subprocess.run(
            ["tectonic", tex_path, "--outdir", tmpdir],
            capture_output=True,
            text=True
        )
        
        if resultado.returncode != 0:
            return {"status": "error", "mensaje": resultado.stderr}
            
        with open(pdf_path, "rb") as f_pdf:
            pdf_b64 = base64.b64encode(f_pdf.read()).decode("utf-8")
            
        return {
            "status": "success",
            "archivo_nombre": "CV_Cesar_Ancieta.pdf",
            "pdf_base64": pdf_b64
        }

sse = SseServerTransport("/messages/")

async def handle_sse(request):
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp._mcp_server.run(
            streams[0], streams[1], mcp._mcp_server.create_initialization_options()
        )

async def handle_messages(request_or_scope, receive=None, send=None):
    if receive is not None and send is not None:
        await sse.handle_post_message(request_or_scope, receive, send)
    else:
        request = request_or_scope
        await sse.handle_post_message(request.scope, request.receive, request._send)

async def health_check(request):
    return JSONResponse({"status": "ok", "service": "LatexCompilerService"})

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

routes = [
    Route("/", endpoint=health_check, methods=["GET"]),
    Route("/sse", endpoint=handle_sse, methods=["GET"]),
    Route("/mcp", endpoint=handle_sse, methods=["GET"]),
    Mount("/messages", app=handle_messages),
]

app = Starlette(debug=False, routes=routes, middleware=middleware)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=port, forwarded_allow_ips="*")
