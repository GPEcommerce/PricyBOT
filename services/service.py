from __future__ import annotations
import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from playwright.async_api import async_playwright, Browser, Playwright, BrowserContext

# =====================================================================
# Helpers de Leitura de Arquivo e Formatação de Dados (Mantidos)
# =====================================================================

def _img_formula(url: str) -> str:
    """Gera uma fórmula de imagem para planilhas."""
    return f'=IMAGEM("{url}")' if url else ""

def _parse_float_maybe(v: Any) -> Optional[float]:
    """Converte um valor para float, tratando formatações comuns."""
    if v is None:
        return None
    try:
        if isinstance(v, str):
            v = v.strip().replace("R$", "").replace(".", "").replace(",", ".")
        return float(v)
    except (ValueError, TypeError):
        return None

def _row_viabilidade(item: Dict[str, Any], termo: str) -> Dict[str, Any]:
    """Formata a linha de saída para o serviço de Viabilidade."""
    return {
        "Foto": _img_formula(item.get("imagem_url", "")),
        "Anuncio": item.get("titulo", ""),
        "Nome": item.get("titulo", ""),
        "Preço anunciado": item.get("preco", 0.0),
        "Quantidade de vendas": item.get("vendidos_recente", 0),
        "vendas": item.get("vendidos_recente", 0),
        "Giro": item.get("vendidos_recente", 0),
        "Estado": item.get("estado_loja", ""),
        "Link do anuncio": item.get("produto_url", ""),
        "link": item.get("produto_url", ""),
        "Pesquisa": termo,
    }

def _row_pma(item: Dict[str, Any], termo: str, preco_maximo: float) -> Optional[Dict[str, Any]]:
    """Formata a linha de saída para o serviço de PMA (Preço Máximo Anunciado)."""
    preco_anunciado = float(item.get("preco") or 0.0)
    if preco_maximo is None or preco_anunciado >= preco_maximo:
        return None
    desvio = round(((preco_maximo - preco_anunciado) / preco_maximo) * 100, 2) if preco_maximo > 0 else 0.0

    return {
        "Foto": _img_formula(item.get("imagem_url", "")),
        "Anuncio": item.get("titulo", ""),
        "Nome": item.get("titulo", ""),
        "Preço anunciado": preco_anunciado,
        "Preço sugerido": float(preco_maximo),
        "Desvio": desvio,
        "Quantidade de vendas": item.get("vendidos_recente", 0),
        "vendas": item.get("vendidos_recente", 0),
        "Estado": item.get("estado_loja", ""),
        "Link do anuncio": item.get("produto_url", ""),
        "link": item.get("produto_url", ""),
        "Pesquisa": termo,
    }

def _row_manutencao(item: Dict[str, Any], termo: str, nosso_preco: float) -> Optional[Dict[str, Any]]:
    """Formata a linha de saída para o serviço de Manutenção de Margem."""
    preco_anunciado = float(item.get("preco") or 0.0)
    if nosso_preco is None or preco_anunciado >= nosso_preco:
        return None
    diff_pct = round(((nosso_preco - preco_anunciado) / nosso_preco) * 100, 2) if nosso_preco > 0 else 0.0

    return {
        "Foto": _img_formula(item.get("imagem_url", "")),
        "Anuncio": item.get("titulo", ""),
        "Nome": item.get("titulo", ""),
        "preco_anunciado": preco_anunciado,
        "Preço anunciado": preco_anunciado,
        "nosso_preco": float(nosso_preco),
        "diferenca_porcentagem": diff_pct,
        "diferenca_reais": round(nosso_preco - preco_anunciado, 2),
        "Quantidade de vendas": item.get("vendidos_recente", 0),
        "vendas": item.get("vendidos_recente", 0),
        "Estado": item.get("estado_loja", ""),
        "Link do anuncio": item.get("produto_url", ""),
        "link": item.get("produto_url", ""),
        "Pesquisa": termo,
    }

_TERMO_CANDIDATES = ["termo", "produto", "palavra", "nome", "descricao", "descrição"]
_PRECO_CANDIDATES = ["preco", "preço", "pma", "nosso_preco", "price", "valor"]

def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in cols_lower:
            return cols_lower[cand]
    return None

def _read_terms_from_file(path: str) -> List[Tuple[str, Optional[float]]]:
    """Lê um arquivo .csv ou .xlsx e extrai os termos e preços."""
    if path.lower().endswith(".csv"):
        try:
            df = pd.read_csv(path, sep=';', dtype=str, encoding="utf-8")
        except Exception:
            df = pd.read_csv(path, sep=',', dtype=str, encoding="utf-8")
    elif path.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(path, dtype=str, engine="openpyxl")
    else:
        raise ValueError("Formato de arquivo não suportado. Envie .csv ou .xlsx")

    df.columns = [str(c).strip() for c in df.columns]
    col_termo = _find_col(df, _TERMO_CANDIDATES)
    col_preco = _find_col(df, _PRECO_CANDIDATES)

    if not col_termo:
        raise ValueError(f"Coluna de termo não encontrada. Use uma de: {', '.join(_TERMO_CANDIDATES)}")

    terms = []
    for _, row in df.iterrows():
        termo = (row.get(col_termo) or "").strip()
        if not termo:
            continue
        preco_val = _parse_float_maybe(row.get(col_preco)) if col_preco else None
        terms.append((termo, preco_val))
    return terms


# =====================================================================
# Serviço de Pesquisa de Mercado com Playwright
# =====================================================================

class ShopeeMarketResearchService:
    """
    Serviço que orquestra um navegador headless com Playwright para coletar
    dados de pesquisa da Shopee de forma robusta e eficiente.
    """
    def __init__(self, *, max_pages: int = 3, page_size: int = 50, delay_between_pages: float = 0.8):
        self.max_pages = max_pages
        self.page_size = page_size
        self.delay_between_pages = delay_between_pages
        
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None

    async def _initialize_browser(self):
        """
        Inicializa uma única instância do Playwright e do navegador Chromium
        para ser reutilizada por todas as pesquisas, otimizando o desempenho.
        """
        if not self.browser:
            print("Inicializando navegador headless...")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
            print("Navegador pronto.")

    async def _fetch_all_pages(self, termo: str) -> List[Dict[str, Any]]:
        """
        Executa a pesquisa para um termo, interceptando as chamadas de API
        em segundo plano para obter os dados diretamente em formato JSON.
        """
        await self._initialize_browser()
        if not self.context:
            raise RuntimeError("Contexto do navegador não foi inicializado.")

        page = await self.context.new_page()
        all_items = []
        
        try:
            print(f"Iniciando pesquisa para o termo: '{termo}'")
            for page_num in range(self.max_pages):
                search_url = f"https://shopee.com.br/search?keyword={termo.replace(' ', '%20')}&page={page_num}"
                
                # Executa a navegação e a espera pela resposta da API em paralelo
                _, response = await asyncio.gather(
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000),
                    page.wait_for_response(
                        lambda res: "/api/v4/search/search_items" in res.url and res.status == 200,
                        timeout=30000
                    )
                )
                
                data = await response.json()

                items = data.get("items", [])
                if not items:
                    print(f"Nenhum item encontrado na página {page_num + 1} para '{termo}'. Encerrando busca.")
                    break
                
                normalized_items = self._normalize_api_items(items)
                all_items.extend(normalized_items)
                print(f"Página {page_num + 1}: {len(normalized_items)} itens coletados. Total: {len(all_items)}.")

                await asyncio.sleep(self.delay_between_pages)
        
        except Exception as e:
            print(f"ERRO ao pesquisar o termo '{termo}': {e}")
        finally:
            await page.close()
            
        return all_items

    def _normalize_api_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Converte a estrutura de dados complexa da API da Shopee para um
        formato limpo e padronizado usado pelo resto da aplicação.
        """
        results = []
        for item in items:
            item_basic = item.get("item_basic", {})
            if not item_basic:
                continue
            
            shop_id = item_basic.get('shopid')
            item_id = item_basic.get('itemid')
            
            results.append({
                "titulo": item_basic.get("name", ""),
                "preco": (item_basic.get("price", 0) or 0) / 100000.0,
                "vendidos_recente": item_basic.get("historical_sold", item_basic.get("sold", 0)),
                "estado_loja": item_basic.get("shop_location", ""),
                "imagem_url": f"https://cf.shopee.com.br/file/{item_basic.get('image')}_tn" if item_basic.get('image') else "",
                "produto_url": f"https://shopee.com.br/product/{shop_id}/{item_id}" if shop_id and item_id else ""
            })
        return results

    async def fechar(self):
        """
        Encerra o navegador e a instância do Playwright de forma segura
        para liberar os recursos.
        """
        print("Encerrando navegador headless...")
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("Recursos liberados.")

    # =====================================================================
    # Métodos Públicos (Interface da Classe - Sem Alterações)
    # =====================================================================
    
    async def analisar_viabilidade(self, termo: str | None = None, caminho_arquivo: str | None = None) -> List[Dict[str, Any]]:
        resultados_finais = []
        if caminho_arquivo:
            termos = _read_terms_from_file(caminho_arquivo)
            for t, _ in termos:
                raw_items = await self._fetch_all_pages(t)
                resultados_finais.extend([_row_viabilidade(item, t) for item in raw_items])
        elif termo:
            raw_items = await self._fetch_all_pages(termo)
            resultados_finais.extend([_row_viabilidade(item, termo) for item in raw_items])
        
        return resultados_finais

    async def analisar_pma(self, termo: str | None = None, preco_maximo: float | None = None, caminho_arquivo: str | None = None) -> List[Dict[str, Any]]:
        resultados_finais = []
        if caminho_arquivo:
            termos = _read_terms_from_file(caminho_arquivo)
            for t, preco in termos:
                if preco is None: continue
                raw_items = await self._fetch_all_pages(t)
                resultados_finais.extend([res for item in raw_items if (res := _row_pma(item, t, preco))])
        elif termo and preco_maximo is not None:
            raw_items = await self._fetch_all_pages(termo)
            resultados_finais.extend([res for item in raw_items if (res := _row_pma(item, termo, preco_maximo))])
        
        return resultados_finais

    async def analisar_manutencao_margem(self, termo: str | None = None, preco_nosso: float | None = None, caminho_arquivo: str | None = None) -> List[Dict[str, Any]]:
        resultados_finais = []
        if caminho_arquivo:
            termos = _read_terms_from_file(caminho_arquivo)
            for t, preco in termos:
                if preco is None: continue
                raw_items = await self._fetch_all_pages(t)
                resultados_finais.extend([res for item in raw_items if (res := _row_manutencao(item, t, preco))])
        elif termo and preco_nosso is not None:
            raw_items = await self._fetch_all_pages(termo)
            resultados_finais.extend([res for item in raw_items if (res := _row_manutencao(item, termo, preco_nosso))])

        return resultados_finais