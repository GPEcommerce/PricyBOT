from __future__ import annotations
import asyncio
import sys

# Bloco de código para corrigir o erro no Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
import shutil
import uuid
from typing import List, Dict, Any
from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import Optional

from services.service import ShopeeMarketResearchService

# -------------------- Inicialização --------------------
app = FastAPI(title="Automações de E-commerce (HTTP-only)")

# Pastas necessárias
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("uploads_temp", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# -------------------- Healthcheck --------------------
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

# -------------------- Menu --------------------
@app.get("/", response_class=HTMLResponse)
async def menu_principal(request: Request):
    return templates.TemplateResponse("menu.html", {"request": request})

# -------------------- Render resultados --------------------
def _prepare_results_response(
    request: Request,
    resultados: List[Dict[str, Any]],
    titulo_pesquisa: str,
    tipo_servico: str
) -> HTMLResponse:
    if not resultados:
        headers, unique_states, unique_searches = [], [], []
    else:
        ORDEM_COLUNAS_DESEJADA = [
            "Foto", "Anuncio", "Nome",
            "Preço anunciado", "nosso_preco", "Preço sugerido", "Desvio",
            "diferenca_porcentagem", "diferenca_reais",
            "Quantidade de vendas", "vendas", "Giro",
            "Estado",
            "Link do anuncio", "link",
            "Pesquisa"
        ]
        all_keys = set(key for item in resultados for key in item.keys())
        headers_ordenados = [h for h in ORDEM_COLUNAS_DESEJADA if h in all_keys]
        headers_extras = sorted([h for h in all_keys if h not in ORDEM_COLUNAS_DESEJADA])
        headers = headers_ordenados + headers_extras
        unique_states = sorted(list({item.get("Estado", "") for item in resultados if item.get("Estado")}))
        unique_searches = sorted(list({item.get("Pesquisa", "") for item in resultados if item.get("Pesquisa")}))

    return templates.TemplateResponse(
        "resultados.html",
        {
            "request": request,
            "resultados": resultados,
            "titulo_pesquisa": titulo_pesquisa,
            "tipo_servico_raw": tipo_servico,
            "headers": headers,
            "states": unique_states,
            "searches": unique_searches
        }
    )

# -------------------- Pesquisa (HTML) --------------------
@app.post("/shopee/pesquisar", response_class=HTMLResponse)
async def pesquisar_shopee(
    request: Request,
    tipo_servico: str = Form(...),
    termo_busca: str = Form(None),
    preco: Optional[str] = Form(None),
    arquivo: UploadFile = File(None)
):
    service = ShopeeMarketResearchService()
    caminho_arquivo_temporario = None

    try:
        resultados: List[Dict[str, Any]] = []
        titulo_pesquisa = ""
        preco_float = None
        if preco and preco.strip():
            try:
                preco_float = float(preco.replace(",", "."))
            except Exception:
                preco_float = None

        if arquivo and arquivo.filename:
            # Pesquisa em lote via arquivo
            titulo_pesquisa = f"Arquivo: {arquivo.filename}"
            caminho_arquivo_temporario = f"uploads_temp/{uuid.uuid4()}_{arquivo.filename}"
            with open(caminho_arquivo_temporario, "wb") as buffer:
                shutil.copyfileobj(arquivo.file, buffer)

            if tipo_servico == "viabilidade":
                resultados = await service.analisar_viabilidade(caminho_arquivo=caminho_arquivo_temporario)
            elif tipo_servico == "pma":
                resultados = await service.analisar_pma(caminho_arquivo=caminho_arquivo_temporario)
            elif tipo_servico == "manutencao_margem":
                resultados = await service.analisar_manutencao_margem(caminho_arquivo=caminho_arquivo_temporario)

        elif termo_busca:
            # Pesquisa unitária
            titulo_pesquisa = termo_busca
            if tipo_servico == "viabilidade":
                resultados = await service.analisar_viabilidade(termo=termo_busca)
            elif tipo_servico == "pma":
                resultados = await service.analisar_pma(termo=termo_busca, preco_maximo=preco_float)
            elif tipo_servico == "manutencao_margem":
                resultados = await service.analisar_manutencao_margem(termo=termo_busca, preco_nosso=preco_float)

        return _prepare_results_response(request, resultados, titulo_pesquisa, tipo_servico)

    except Exception as e:
        return templates.TemplateResponse("error.html", {"request": request, "detail": str(e)}, status_code=500)

    finally:
        await service.fechar()
        if caminho_arquivo_temporario and os.path.exists(caminho_arquivo_temporario):
            os.remove(caminho_arquivo_temporario)

# -------------------- Pesquisa (JSON para “Nova Pesquisa”) --------------------
@app.post("/api/shopee/add_search", response_class=JSONResponse)
async def add_shopee_search(request: Request):
    service = ShopeeMarketResearchService()
    try:
        data = await request.json()
        tipo_servico = data.get("tipo_servico")
        termo_busca = data.get("termo_busca")
        preco_str = data.get("preco")

        preco_float = None
        if preco_str is not None:
            try:
                preco_float = float(str(preco_str).replace(",", "."))
            except Exception:
                preco_float = None

        resultados: List[Dict[str, Any]] = []
        if tipo_servico == "viabilidade":
            resultados = await service.analisar_viabilidade(termo=termo_busca)
        elif tipo_servico == "pma":
            resultados = await service.analisar_pma(termo=termo_busca, preco_maximo=preco_float)
        elif tipo_servico == "manutencao_margem":
            resultados = await service.analisar_manutencao_margem(termo=termo_busca, preco_nosso=preco_float)

        return JSONResponse(content=resultados)

    except Exception as e:
        return JSONResponse(content={"error": "An unexpected error occurred", "detail": str(e)}, status_code=500)
    finally:
        await service.fechar()
