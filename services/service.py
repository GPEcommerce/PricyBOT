# services/service.py
from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from clients.shopee_search import ShopeeSearchClient


# ==============================
# Helpers de transformação
# ==============================

def _img_formula(url: str) -> str:
    return f'=IMAGEM("{url}")' if url else ""


def _parse_float_maybe(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, str):
            v = v.strip().replace("R$", "").replace(".", "").replace(",", ".")
        return float(v)
    except Exception:
        return None


# ==============================
# Normalizações de saída
# (PADRÃO DE COLUNAS COMPATÍVEL
#  COM O FRONT EXISTENTE)
# ==============================

def _row_viabilidade(item: Dict[str, Any], termo: str) -> Dict[str, Any]:
    """Linha de saída para análise de viabilidade."""
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
    """Linha de saída para análise de PMA (somente quando anunciado < PMA)."""
    preco_anunciado = float(item.get("preco") or 0.0)
    if preco_maximo is None or preco_anunciado >= preco_maximo:
        return None
    desvio = round(((preco_maximo - preco_anunciado) / preco_maximo) * 100, 2) if preco_maximo else 0.0

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
    """Linha de saída para manutenção de margem (somente quando anunciado < nosso_preco)."""
    preco_anunciado = float(item.get("preco") or 0.0)
    if nosso_preco is None or preco_anunciado >= nosso_preco:
        return None
    diff_pct = round(((nosso_preco - preco_anunciado) / nosso_preco) * 100, 2) if nosso_preco else 0.0

    return {
        "Foto": _img_formula(item.get("imagem_url", "")),
        "Anuncio": item.get("titulo", ""),
        "Nome": item.get("titulo", ""),
        "preco_anunciado": preco_anunciado,               # compat
        "Preço anunciado": preco_anunciado,               # compat
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


# ==============================
# Leitura de arquivos (.csv/.xlsx)
# Suporta colunas flexíveis:
#  - termo: ["termo","produto","palavra","nome","descricao"]
#  - preco: ["preco","preço","pma","nosso_preco","price"]
# ==============================

_TERMO_CANDIDATES = ["termo", "produto", "palavra", "nome", "descricao", "descrição"]
_PRECO_CANDIDATES = ["preco", "preço", "pma", "nosso_preco", "price", "valor"]

def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in cols_lower:
            return cols_lower[cand]
    return None


def _read_terms_from_file(path: str) -> List[Tuple[str, Optional[float]]]:
    """
    Lê um arquivo .csv ou .xlsx e retorna uma lista de (termo, preco_opcional).
    Para CSV, faz uma tentativa com ; e ,.
    """
    terms: List[Tuple[str, Optional[float]]] = []
    if path.lower().endswith(".csv"):
        tried = []
        for sep in [";", ","]:
            try:
                df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8", engine="python")
                tried.append(sep)
                break
            except Exception:
                df = None
        if df is None:  # última tentativa "solta"
            df = pd.read_csv(path, dtype=str, engine="python")

    elif path.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(path, dtype=str, engine="openpyxl")
    else:
        raise ValueError("Formato de arquivo não suportado. Envie .csv ou .xlsx")

    # Normaliza colunas
    df.columns = [str(c).strip() for c in df.columns]
    col_termo = _find_col(df, _TERMO_CANDIDATES)
    col_preco = _find_col(df, _PRECO_CANDIDATES)

    if not col_termo:
        raise ValueError(
            "Arquivo inválido: não encontrei coluna de termo. "
            f"Tente uma das seguintes: {', '.join(_TERMO_CANDIDATES)}"
        )

    for _, row in df.iterrows():
        termo = (row.get(col_termo) or "").strip()
        if not termo:
            continue
        preco_val = None
        if col_preco:
            preco_val = _parse_float_maybe(row.get(col_preco))
        terms.append((termo, preco_val))

    return terms


# ==============================
# Serviço principal (HTTP-only)
# ==============================

class ShopeeMarketResearchService:
    """
    Versão HTTP-only do serviço. Mantém as mesmas assinaturas públicas usadas pelo app:
      - analisar_viabilidade(termo=...) ou (caminho_arquivo=...)
      - analisar_pma(termo/preco_maximo) idem
      - analisar_manutencao_margem(termo/preco_nosso) idem
    """

    def __init__(self, *, max_pages: int = 3, page_size: int = 50, delay_between_pages: float = 0.35):
        self.client = ShopeeSearchClient()
        self.max_pages = max_pages
        self.page_size = page_size
        self.delay_between_pages = delay_between_pages

    # ---------- Núcleo de coleta ----------
    async def _fetch_all_pages(self, termo: str) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for page in range(self.max_pages):
            payload = await self.client.search_keyword(termo, page=page, limit=self.page_size)
            items = self.client.normalize_items(payload)
            if not items:
                break
            results.extend(items)
            # evita agressividade excessiva
            await asyncio.sleep(self.delay_between_pages)
        return results

    # ---------- Execução por termo ----------
    async def _viabilidade_por_termo(self, termo: str) -> List[Dict[str, Any]]:
        raw = await self._fetch_all_pages(termo)
        out: List[Dict[str, Any]] = []
        for it in raw:
            # critério simples: usa vendidos recentes como proxy de giro
            r = _row_viabilidade(it, termo)
            out.append(r)
        return out

    async def _pma_por_termo(self, termo: str, preco_maximo: Optional[float]) -> List[Dict[str, Any]]:
        if preco_maximo is None:
            return []
        raw = await self._fetch_all_pages(termo)
        out: List[Dict[str, Any]] = []
        for it in raw:
            r = _row_pma(it, termo, float(preco_maximo))
            if r:
                out.append(r)
        return out

    async def _manutencao_por_termo(self, termo: str, preco_nosso: Optional[float]) -> List[Dict[str, Any]]:
        if preco_nosso is None:
            return []
        raw = await self._fetch_all_pages(termo)
        out: List[Dict[str, Any]] = []
        for it in raw:
            r = _row_manutencao(it, termo, float(preco_nosso))
            if r:
                out.append(r)
        return out

    # ---------- APIs públicas (mantidas) ----------
    async def analisar_viabilidade(
        self,
        termo: Optional[str] = None,
        caminho_arquivo: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if caminho_arquivo:
            termos = _read_terms_from_file(caminho_arquivo)
            resultados: List[Dict[str, Any]] = []
            for t, _ in termos:
                resultados.extend(await self._viabilidade_por_termo(t))
            return resultados
        elif termo:
            return await self._viabilidade_por_termo(termo)
        else:
            return []

    async def analisar_pma(
        self,
        termo: Optional[str] = None,
        preco_maximo: Optional[float] = None,
        caminho_arquivo: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if caminho_arquivo:
            termos = _read_terms_from_file(caminho_arquivo)
            resultados: List[Dict[str, Any]] = []
            for t, preco in termos:
                if preco is None:
                    # pula linhas sem preço
                    continue
                resultados.extend(await self._pma_por_termo(t, preco))
            return resultados
        elif termo:
            return await self._pma_por_termo(termo, preco_maximo)
        else:
            return []

    async def analisar_manutencao_margem(
        self,
        termo: Optional[str] = None,
        preco_nosso: Optional[float] = None,
        caminho_arquivo: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if caminho_arquivo:
            termos = _read_terms_from_file(caminho_arquivo)
            resultados: List[Dict[str, Any]] = []
            for t, preco in termos:
                if preco is None:
                    continue
                resultados.extend(await self._manutencao_por_termo(t, preco))
            return resultados
        elif termo:
            return await self._manutencao_por_termo(termo, preco_nosso)
        else:
            return []

    # ---------- Compatibilidade ----------
    async def fechar(self):
        """Mantido por compatibilidade com o app atual (chamado no finally)."""
        await self.client.aclose()
