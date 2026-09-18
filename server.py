import os
import json
import tempfile
import subprocess
import base64
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

port = int(os.environ.get("PORT", 10000))

def compilar_cv(codigo_latex: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "cv.tex")
        pdf_path = os.path.join(tmpdir, "cv.pdf")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(codigo_latex)
        res = subprocess.run(["tectonic", tex_path, "--outdir", tmpdir], capture_output=True, text=True)
        if res.returncode != 0:
            return {"status": "error", "mensaje": res.stderr}
        with open(pdf_path, "rb") as f_pdf:
            pdf_b64 = base64.b64encode(f_pdf.read()).decode("utf-8")
        return {"status": "success", "archivo_nombre": "CV_Cesar_Ancieta.pdf", "pdf_base64": pdf_b64}

async def handle_mcp(request):
    if request.method in ["GET", "HEAD"]:
        return JSONResponse({"status": "ok", "service": "LatexCompilerMCP"})
    
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}, status_code=400)
    
    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "LatexCompilerService", "version": "1.0.0"}
            }
        })
    
    elif method == "notifications/initialized":
        return Response(status_code=204)
    
    elif method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [{
                    "name": "compilar_cv_latex",
                    "description": "Compila codigo LaTeX a PDF con Tectonic y retorna el binario en Base64.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "codigo_latex": {"type": "string", "description": "Codigo LaTeX del CV"}
                        },
                        "required": ["codigo_latex"]
                    }
                }]
            }
        })
    
    elif method == "tools/call":
        args = params.get("arguments", {})
        latex_code = args.get("codigo_latex", "")
        resultado = compilar_cv(latex_code)
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(resultado)}],
                "isError": resultado.get("status") == "error"
            }
        })
    
    elif method == "ping":
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})
    
    return JSONResponse({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": "Method not found"}
    })

middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

routes = [
    Route("/", endpoint=handle_mcp, methods=["GET", "HEAD", "POST"]),
    Route("/mcp", endpoint=handle_mcp, methods=["GET", "HEAD", "POST"]),
    Route("/sse", endpoint=handle_mcp, methods=["GET", "HEAD", "POST"]),
]

app = Starlette(routes=routes, middleware=middleware)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=port)
