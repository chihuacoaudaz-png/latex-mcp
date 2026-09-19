import os
import json
import tempfile
import subprocess
import base64
import re
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from mcp.server.fastmcp import FastMCP

port = int(os.environ.get("PORT", 10000))

# ---------------------------------------------------------
# Linter y Sanitizador de LaTeX (Anti-alucinaciones)
# ---------------------------------------------------------
def sanitize_latex(latex_code: str) -> str:
    """
    Sanitiza y limpia rigurosamente el codigo LaTeX antes de enviar a Tectonic:
    1. Remueve bloques de markdown fences (```latex ... ```).
    2. Purga artefactos de citacion de Gemini/Gems ([cite: 1], site 1, etc.).
    3. Asegura el encabezado canonico 'CESAR CONTRERAS ANCIETA' (sin tildes y con C).
    4. Escapa porcentajes sueltos ('80%' -> '80\\%') y ampersands ('Python & SQL' -> 'Python \\& SQL').
    """
    s = latex_code.strip()
    
    # Remover fences de Markdown si vinieran incluidos
    if s.startswith("```latex"):
        s = s[8:]
    elif s.startswith("```tex"):
        s = s[6:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()

    # Purgar artefactos de citacion
    cite_patterns = [
        r'\[\s*(?:cite|site)\s*:\s*[\d\s,]+\]',
        r'\[\s*(?:cite|site)\s+[\d\s,]+\]',
        r'\b(?:cite|site)\s*:\s*\d+\b',
        r'\b(?:cite|site)\s+\d+\b',
        r'\[\s*\d+\s*\]'
    ]
    for pat in cite_patterns:
        s = re.sub(pat, '', s, flags=re.IGNORECASE)

    # Convertir caracteres unicode especiales a comandos LaTeX validos
    s = s.replace('\u2022', r'\textbullet{} ')  # Bala unicode •
    s = s.replace('\u00b7', r' \textbar{} ')   # Punto medio ·
    s = s.replace('\u2013', '--')             # En-dash –
    s = s.replace('\u2014', '---')            # Em-dash —
    s = s.replace('\ufffd', '')               # Caracter corrupto de reemplazo

    # Asegurar nombre canonico en encabezados
    s = re.sub(r'CESAR\s+ANCIETA', 'CESAR CONTRERAS ANCIETA', s, flags=re.IGNORECASE)
    s = re.sub(r'CÉSAR\s+ANCIETA', 'CESAR CONTRERAS ANCIETA', s, flags=re.IGNORECASE)
    s = re.sub(r'CESAR\s+CONTRERAS\s+ANSIETA', 'CESAR CONTRERAS ANCIETA', s, flags=re.IGNORECASE)
    s = re.sub(r'CÉSAR\s+CONTRERAS\s+ANSIETA', 'CESAR CONTRERAS ANCIETA', s, flags=re.IGNORECASE)
    s = re.sub(r'CÉSAR\s+CONTRERAS\s+ANCIETA', 'CESAR CONTRERAS ANCIETA', s, flags=re.IGNORECASE)
    s = re.sub(r'CV_Cesar_Ancieta\.pdf', 'CV_Cesar_Contreras_Ancieta.pdf', s, flags=re.IGNORECASE)

    # Escapar porcentajes sueltos
    s = re.sub(r'(?<=\d)%(?=[^\\])', r'\\%', s)
    s = re.sub(r'(?<=\d)%$', r'\\%', s, flags=re.MULTILINE)

    # Escapar ampersands en texto plano
    s = re.sub(r'(?<=[a-zA-Z0-9])\s*&\s*(?=[a-zA-Z0-9])', r' \\& ', s)

    # Normalizar espacios repetidos
    s = re.sub(r'[ \t]{2,}', ' ', s)

    return s

def compilar_cv(codigo_latex: str) -> dict:
    """Compila codigo LaTeX con Tectonic y retorna diccionario con base64 o error."""
    clean_code = sanitize_latex(codigo_latex)
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "cv.tex")
        pdf_path = os.path.join(tmpdir, "cv.pdf")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(clean_code)
        
        try:
            res = subprocess.run(["tectonic", tex_path, "--outdir", tmpdir], capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            return {"status": "error", "mensaje": "Tiempo de compilacion excedido (timeout 90s)."}
        except Exception as e:
            return {"status": "error", "mensaje": f"Fallo al ejecutar tectonic: {str(e)}"}

        if res.returncode != 0:
            return {"status": "error", "mensaje": res.stderr or res.stdout or "Error de sintaxis LaTeX en Tectonic."}
        
        if not os.path.exists(pdf_path):
            return {"status": "error", "mensaje": "El archivo PDF no fue generado por Tectonic."}

        with open(pdf_path, "rb") as f_pdf:
            pdf_bytes = f_pdf.read()
            pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
        
        return {
            "status": "success",
            "archivo_nombre": "CV Cesar Contreras Ancieta.pdf",
            "bytes_length": len(pdf_bytes),
            "pdf_base64": pdf_b64
        }

# ---------------------------------------------------------
# MCP Server con FastMCP (Soporte SSE /sse y /messages)
# ---------------------------------------------------------
mcp = FastMCP("LatexCompilerService")

@mcp.tool()
def compilar_cv_latex(codigo_latex: str) -> str:
    """Compila codigo LaTeX a PDF con Tectonic y retorna el binario en Base64."""
    resultado = compilar_cv(codigo_latex)
    return json.dumps(resultado)

sse_subapp = mcp.sse_app()

# ---------------------------------------------------------
# Handlers JSON-RPC 2.0 y REST Directo
# ---------------------------------------------------------
async def handle_direct_compile(request):
    """Endpoint REST directo POST /compile o /compilar."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "mensaje": "Cuerpo de solicitud invalido (se esperaba JSON)."}, status_code=400)
    
    latex_code = body.get("codigo_latex") or body.get("latex") or body.get("code") or ""
    if not latex_code:
        return JSONResponse({"status": "error", "mensaje": "El campo 'codigo_latex' es requerido."}, status_code=400)
    
    resultado = compilar_cv(latex_code)
    status_code = 200 if resultado.get("status") == "success" else 422
    return JSONResponse(resultado, status_code=status_code)

async def handle_direct_compile_pdf(request):
    """Endpoint REST directo POST /compile/pdf que retorna el archivo binario PDF."""
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            body = await request.json()
            latex_code = body.get("codigo_latex") or body.get("latex") or body.get("code") or ""
        else:
            raw_body = await request.body()
            latex_code = raw_body.decode("utf-8", errors="ignore")
    except Exception as e:
        return Response(f"Error procesando solicitud: {str(e)}", status_code=400)

    if not latex_code:
        return Response("El codigo LaTeX es requerido en el cuerpo.", status_code=400)

    resultado = compilar_cv(latex_code)
    if resultado.get("status") != "success":
        return Response(f"Error de compilacion: {resultado.get('mensaje')}", status_code=422)

    pdf_bytes = base64.b64decode(resultado["pdf_base64"])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="CV Cesar Contreras Ancieta.pdf"'}
    )

async def handle_mcp_rpc(request):
    """Handler JSON-RPC 2.0 en POST / y /mcp para compatibilidad estricta MCP."""
    if request.method in ["GET", "HEAD"]:
        return JSONResponse({
            "status": "ok",
            "service": "LatexCompilerMCP",
            "version": "1.1.0",
            "engine": "Tectonic",
            "mcp_sse_endpoint": "/sse",
            "rest_compile_endpoint": "/compile"
        })
    
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
                "serverInfo": {"name": "LatexCompilerService", "version": "1.1.0"}
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
        args = params.get("arguments", {}) or params.get("parameters", {})
        latex_code = args.get("codigo_latex") or args.get("latex") or args.get("code") or ""
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
        "error": {"code": -32601, "message": f"Method '{method}' not found"}
    })

middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

# Unificar rutas: REST + JSON-RPC + MCP SSE
custom_routes = [
    Route("/", endpoint=handle_mcp_rpc, methods=["GET", "HEAD", "POST"]),
    Route("/mcp", endpoint=handle_mcp_rpc, methods=["GET", "HEAD", "POST"]),
    Route("/compile", endpoint=handle_direct_compile, methods=["POST"]),
    Route("/compilar", endpoint=handle_direct_compile, methods=["POST"]),
    Route("/compile/pdf", endpoint=handle_direct_compile_pdf, methods=["POST"]),
    Route("/compilar/pdf", endpoint=handle_direct_compile_pdf, methods=["POST"]),
    Route("/health", endpoint=lambda r: JSONResponse({"status": "ok", "service": "LatexCompilerMCP"}), methods=["GET", "HEAD"]),
]

app = Starlette(routes=custom_routes + list(sse_subapp.routes), middleware=middleware)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=port)
