import os
import tempfile
import subprocess
import base64
from mcp.server.fastmcp import FastMCP

port = int(os.environ.get("PORT", 10000))
mcp = FastMCP("LatexCompilerService", host="0.0.0.0", port=port)

@mcp.tool()
def compilar_cv_latex(codigo_latex: str) -> dict:
    """Recibe el código LaTeX del CV, lo compila con Tectonic y retorna el PDF en base64."""
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

if __name__ == "__main__":
    mcp.run(transport="sse")
