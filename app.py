import os
import shutil
import uuid
from typing import Optional, List, Dict, Any
from requests.exceptions import ConnectionError
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

# Importações de negócio e automação
from services.service import ShopeeMarketResearchService
from core.exceptions import LoginRequiredException, EmailVerificationRequiredException
from core.chrome import Chrome

from abrir_chrome import iniciar_chrome, esperar_chrome_pronto
from core.utils import Utils # Usaremos para o screenshot
import time

# --- ESTADO GLOBAL DA APLICAÇÃO ---
# Alteração: O estado agora é usado APENAS para gerenciar o fluxo de login em 2 etapas.
# O navegador não é mais iniciado globalmente.
app_state: Dict[str, Any] = {
    "browser_connection_for_2fa": None,
    "chrome_process_for_2fa": None
}

# --- Alteração: O 'lifespan' foi removido, pois o navegador não é mais gerenciado globalmente.
# Inicialização do FastAPI
app = FastAPI(title="Automações de E-commerce")

# Garante que as pastas necessárias para a aplicação existam
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("uploads_temp", exist_ok=True)
os.makedirs("debug_screenshots", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Alteração: A função 'get_browser_connection' foi removida.

# --- ENDPOINTS PRINCIPAIS DA APLICAÇÃO ---

@app.get("/", response_class=HTMLResponse)
async def menu_principal(request: Request):
    """Serve a página de menu principal (menu.html)."""
    return templates.TemplateResponse("menu.html", {"request": request})

def _prepare_results_response(request: Request, resultados: List[Dict], titulo_pesquisa: str, tipo_servico: str) -> HTMLResponse:
    """Função auxiliar para preparar e renderizar a página de resultados."""
    if not resultados:
        headers, unique_states = [], []
    else:
        ORDEM_COLUNAS_DESEJADA = ["Foto", "Anuncio", "Nome", "Preço anunciado", "nosso_preco", "Preço sugerido", "Desvio", "diferenca_porcentagem", "diferenca_reais", "Quantidade de vendas", "vendas", "Giro", "Estado", "Link do anuncio", "link", "Pesquisa"]
        all_keys = set(key for item in resultados for key in item.keys())
        headers_ordenados = [header for header in ORDEM_COLUNAS_DESEJADA if header in all_keys]
        headers_extras = sorted([header for header in all_keys if header not in ORDEM_COLUNAS_DESEJADA])
        headers = headers_ordenados + headers_extras
        unique_states = sorted(list(set(item.get("Estado", "") for item in resultados if item.get("Estado"))))
        unique_searches = sorted(list(set(item.get("Pesquisa", "") for item in resultados if item.get("Pesquisa"))))
    return templates.TemplateResponse("resultados.html", {
        "request": request,
        "resultados": resultados,
        "titulo_pesquisa": titulo_pesquisa,
        "tipo_servico_raw": tipo_servico,
        "headers": headers,
        "states": unique_states,
        "searches": unique_searches
        })

@app.post("/shopee/pesquisar", response_class=HTMLResponse)
async def pesquisar_shopee(request: Request, tipo_servico: str = Form(...), termo_busca: str = Form(None), preco: Optional[str] = Form(None), arquivo: UploadFile = File(None)):
    # --- Alteração: Lógica de gerenciamento do Chrome movida para dentro da rota ---
    service = None
    caminho_arquivo_temporario = None
    chrome_process = None
    try:
        # Inicia um navegador para esta pesquisa específica
        print("🚀 Iniciando novo processo do Chrome para pesquisa...")
        chrome_process = iniciar_chrome()
        if not chrome_process or not esperar_chrome_pronto(timeout=45):
            raise ConnectionError("Falha ao iniciar ou conectar ao Chrome no container.")
        
        browser = Chrome()
        browser.connect()
        # Fim da inicialização

        service = ShopeeMarketResearchService(browser)
        preco_float = float(preco.replace(',', '.')) if preco and preco.strip() else None
        resultados = []
        titulo_pesquisa = ""

        if arquivo and arquivo.filename:
            # Lógica para pesquisa com arquivo
            titulo_pesquisa = f"Arquivo: {arquivo.filename}"
            caminho_arquivo_temporario = f"uploads_temp/{uuid.uuid4()}_{arquivo.filename}"
            with open(caminho_arquivo_temporario, "wb") as buffer:
                shutil.copyfileobj(arquivo.file, buffer)
            if tipo_servico == 'viabilidade': resultados = await service.analisar_viabilidade(caminho_arquivo=caminho_arquivo_temporario)
            elif tipo_servico == 'pma': resultados = await service.analisar_pma(caminho_arquivo=caminho_arquivo_temporario)
            elif tipo_servico == 'manutencao_margem': resultados = await service.analisar_manutencao_margem(caminho_arquivo=caminho_arquivo_temporario)
        elif termo_busca:
            # Lógica para pesquisa com termo
            titulo_pesquisa = termo_busca
            if tipo_servico == 'viabilidade': resultados = await service.analisar_viabilidade(termo=termo_busca)
            elif tipo_servico == 'pma': resultados = await service.analisar_pma(termo=termo_busca, preco_maximo=preco_float)
            elif tipo_servico == 'manutencao_margem': resultados = await service.analisar_manutencao_margem(termo=termo_busca, preco_nosso=preco_float)
        
        return _prepare_results_response(request, resultados, titulo_pesquisa, tipo_servico)
    
    except LoginRequiredException as e:
        print(f"Login é necessário: {e}. Renderizando página de login.")
        pesquisa_original = {"tipo_servico": tipo_servico, "termo_busca": termo_busca, "preco": preco or ""}
        return templates.TemplateResponse("login_shopee.html", {"request": request, "pesquisa": pesquisa_original})
    
    except ConnectionError as e:
        print(f"ERRO DE CONEXÃO DETECTADO NA ROTA /shopee/pesquisar: {e}")
        return templates.TemplateResponse("browser_error.html", {"request": request, "detail": str(e)}, status_code=503)
    
    except Exception as e:
        print(f"ERRO INESPERADO em /shopee/pesquisar: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "detail": str(e)}, status_code=500)

    finally:
        # --- Alteração: Garante que o navegador iniciado nesta rota seja sempre fechado ---
        if service: await service.fechar()
        if chrome_process and chrome_process.poll() is None:
            print("🔌 Encerrando processo do Chrome da pesquisa...")
            chrome_process.terminate()
            chrome_process.wait()
        if caminho_arquivo_temporario and os.path.exists(caminho_arquivo_temporario):
            os.remove(caminho_arquivo_temporario)

@app.post("/shopee/login_and_search", response_class=HTMLResponse)
async def login_and_search(request: Request, shopee_user: str = Form(...), shopee_pass: str = Form(...), tipo_servico: str = Form(...), termo_busca: str = Form(None), preco: Optional[str] = Form(None)):
    service = None
    chrome_process = None
    manter_processo_aberto = False # Flag para o fluxo de 2FA
    try:
        # Inicia um navegador para a tentativa de login
        print("🚀 Iniciando novo processo do Chrome para login...")
        chrome_process = iniciar_chrome()
        if not chrome_process or not esperar_chrome_pronto(timeout=45):
            raise ConnectionError("Falha ao iniciar ou conectar ao Chrome no container.")
        
        browser = Chrome()
        browser.connect()

        service = ShopeeMarketResearchService(browser)
        preco_float = float(preco.replace(',', '.')) if preco and preco.strip() else None

        await service.fazer_login(shopee_user, shopee_pass)

        # Se o login for direto, executa a pesquisa
        resultados = []
        titulo_pesquisa = termo_busca
        if termo_busca:
            if tipo_servico == 'viabilidade': resultados = await service.analisar_viabilidade(termo=termo_busca)
            elif tipo_servico == 'pma': resultados = await service.analisar_pma(termo=termo_busca, preco_maximo=preco_float)
            elif tipo_servico == 'manutencao_margem': resultados = await service.analisar_manutencao_margem(termo=termo_busca, preco_nosso=preco_float)
        
        return _prepare_results_response(request, resultados, titulo_pesquisa, tipo_servico)

    except EmailVerificationRequiredException:
        print("Pausando a automação para aguardar verificação de e-mail.")
        # --- Alteração: Salva o processo e a conexão no estado global para a próxima etapa ---
        manter_processo_aberto = True
        app_state["browser_connection_for_2fa"] = service.navegador
        app_state["chrome_process_for_2fa"] = chrome_process
        pesquisa_original = {"tipo_servico": tipo_servico, "termo_busca": termo_busca, "preco": preco or ""}
        return templates.TemplateResponse("aguarde_email.html", {"request": request, "pesquisa": pesquisa_original})
    
    except LoginRequiredException as e:
        return templates.TemplateResponse("error.html", {"request": request, "detail": f"Falha no Login: {e}. Verifique suas credenciais e tente novamente."}, status_code=403)
    
    except ConnectionError as e:
        print(f"ERRO DE CONEXÃO DETECTADO NA ROTA /shopee/login_and_search: {e}")
        return templates.TemplateResponse("browser_error.html", {"request": request, "detail": str(e)}, status_code=503)

    except Exception as e:
        print(f"ERRO INESPERADO em /shopee/login_and_search: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "detail": str(e)}, status_code=500)

    finally:
        # --- Alteração: Só fecha o processo se não for necessário para o 2FA ---
        if not manter_processo_aberto:
            if service: await service.fechar()
            if chrome_process and chrome_process.poll() is None:
                print("🔌 Encerrando processo do Chrome do login...")
                chrome_process.terminate()
                chrome_process.wait()

@app.post("/api/shopee/add_search", response_class=JSONResponse)
async def add_shopee_search(request: Request):
    service = None
    chrome_process = None
    try:
        # Inicia um navegador para esta pesquisa específica
        print("🚀 Iniciando novo processo do Chrome para pesquisa API...")
        chrome_process = iniciar_chrome()
        if not chrome_process or not esperar_chrome_pronto(timeout=45):
            raise ConnectionError("Falha ao iniciar ou conectar ao Chrome no container.")
        
        browser = Chrome()
        browser.connect()

        data = await request.json()
        service = ShopeeMarketResearchService(browser)
        
        tipo_servico = data.get("tipo_servico")
        termo_busca = data.get("termo_busca")
        preco_str = data.get("preco")
        preco_float = float(str(preco_str).replace(',', '.')) if preco_str else None
        
        resultados = []
        if tipo_servico == 'viabilidade': resultados = await service.analisar_viabilidade(termo=termo_busca)
        elif tipo_servico == 'pma': resultados = await service.analisar_pma(termo=termo_busca, preco_maximo=preco_float)
        elif tipo_servico == 'manutencao_margem': resultados = await service.analisar_manutencao_margem(termo=termo_busca, preco_nosso=preco_float)
        
        return JSONResponse(content=resultados)

    except LoginRequiredException as e:
        # Este fluxo não suporta login interativo.
        return JSONResponse(content={"error": f"Login Necessário: {e}. Por favor, faça login pela interface principal primeiro."}, status_code=403)
    
    except ConnectionError as e:
        print(f"ERRO DE CONEXÃO DETECTADO NA ROTA /api/shopee/add_search: {e}")
        return JSONResponse(content={"error": "Browser connection failed", "detail": str(e)}, status_code=503)

    except Exception as e:
        print(f"ERRO INESPERADO em /api/shopee/add_search: {e}")
        return JSONResponse(content={"error": "An unexpected error occurred", "detail": str(e)}, status_code=500)

    finally:
        # --- Alteração: Garante que o navegador iniciado nesta rota seja sempre fechado ---
        if service: await service.fechar()
        if chrome_process and chrome_process.poll() is None:
            print("🔌 Encerrando processo do Chrome da pesquisa API...")
            chrome_process.terminate()
            chrome_process.wait()
