# clients/shopee_search.py
from __future__ import annotations
import httpx
from typing import Any, Dict, List, Optional

class ShopeeSearchClient:
    def __init__(
        self,
        base_url: str = "https://shopee.com.br",
        cookies: Optional[Dict[str, str]] = None,
        timeout: float = 15.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(timeout, read=timeout),
            headers={
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/123.0.0.0 Safari/537.36",
                "accept": "application/json, text/plain, */*",
                "accept-language": "pt-BR,pt;q=0.9",
            },
            cookies=cookies or {}
        )

    async def _get(self, url: str, params: Dict[str, Any]) -> httpx.Response:
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                r = await self.client.get(url, params=params)
                r.raise_for_status()
                return r
            except Exception as exc:
                last_exc = exc
                await httpx.AsyncClient().aclose()  # pequena pausa implícita
        raise last_exc

    @staticmethod
    def parse_price(raw: Optional[int | float]) -> float:
        if raw is None:
            return 0.0
        # Tenta /100000 primeiro (padrão visto no seu código atual)
        v = float(raw) / 100000.0
        if 0.01 <= v <= 100000:
            return round(v, 2)
        # Fallback /100
        return round(float(raw) / 100.0, 2)

    def normalize_items(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for it in payload.get("items", []):
            basic = it.get("item_basic", {})
            shop_id = basic.get("shopid")
            item_id = basic.get("itemid")
            image_id = basic.get("image")
            out.append({
                # —— Schema unificado (padronize no projeto inteiro) ——
                "titulo": basic.get("name", ""),
                "preco": self.parse_price(basic.get("price")),
                "vendidos_historico": basic.get("historical_sold", 0),
                "vendidos_recente": basic.get("sold", 0),
                "estado_loja": basic.get("shop_location", ""),
                "imagem_url": f"https://cf.shopee.com.br/file/{image_id}" if image_id else "",
                "produto_url": (
                    f"https://shopee.com.br/product/{shop_id}/{item_id}"
                    if shop_id and item_id else ""
                ),
                "shopid": shop_id,
                "itemid": item_id,
            })
        return out

    async def search_keyword(
        self,
        keyword: str,
        page: int = 0,
        limit: int = 50,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # ⚠️ Substitua pelo endpoint/path exato que você observar no Network
        # Exemplo ilustrativo:
        endpoint = f"{self.base_url}/api/v4/search/search_items"
        params = {"keyword": keyword, "page": page, "limit": limit}
        if extra_params:
            params.update(extra_params)
        r = await self._get(endpoint, params=params)
        return r.json()

    async def aclose(self):
        await self.client.aclose()
