# PricyBOT — Code snippets and quick fixes (2026-09-02)

This file contains small, paste-ready code snippets and files to help get PricyBOT running: a one-line template fix, a cleaned requirements.txt, a sample CSV, and a small normalization helper to unify scraper output keys.

---

## 1) app.py — fix for _prepare_results_response (prevent UnboundLocalError)

Add or replace the empty-results branch so `unique_searches` is defined when `resultados` is empty.

```python
# --- inside app._prepare_results_response ---
if not resultados:
    headers, unique_states, unique_searches = [], [], []
else:
    ORDEM_COLUNAS_DESEJADA = ["Foto", "Anuncio", "Nome", "Preço anunciado", "nosso_preco", "Preço sugerido", "Desvio", "diferenca_porcentagem", "diferenca_reais", "Quantidade de vendas", "vendas", "Giro", "Pesquisa", "Estado", "Link do anuncio", "link"]
    all_keys = set(key for item in resultados for key in item.keys())
    headers_ordenados = [header for header in ORDEM_COLUNAS_DESEJADA if header in all_keys]
    headers_extras = sorted([header for header in all_keys if header not in ORDEM_COLUNAS_DESEJADA])
    headers = headers_ordenados + headers_extras
    unique_states = sorted(list(set(item.get("Estado", "") for item in resultados if item.get("Estado"))))
    unique_searches = sorted(list(set(item.get("Pesquisa", "") for item in resultados if item.get("Pesquisa"))))
```

Place this change in `app.py` where `_prepare_results_response` is implemented (replace the current `if not resultados:` branch).

---

## 2) Cleaned requirements.txt (replace the corrupted file)

Write this content to `requirements.txt` (or use in your environment). This is a minimal cleaned set based on the original list; adjust versions if you need exact pins.

```
fastapi>=0.95
uvicorn>=0.22
pychrome==0.2.4
requests>=2.30
pandas>=2.0
openpyxl>=3.1
opencv-python>=4.6
numpy>=1.24
Jinja2>=3.1
python-dotenv>=1.0
pillow>=9.0
pydantic>=2.1
pyyaml>=6.0
```

Notes:
- If you require many of the originally listed packages, add them explicitly. The important runtime deps here are: fastapi, uvicorn, pychrome, pandas, openpyxl, opencv-python, numpy, requests, jinja2.
- If `opencv-python` import fails in the container, you'll likely need to add OS libs (libsm6, libxrender1, libgtk-3-0 etc) to the Dockerfile and rebuild.

---

## 3) Sample CSV for batch processing

Create a sample CSV file (e.g. `static/modelo_arquivo_pma.csv`) with these contents. The service expects exact headers: `Nome do Produto` and (for PMA / manutencao_margem) `Preço do Produto`.

```
Nome do Produto,Preço do Produto
Fone de ouvido bluetooth,99.90
Cabo USB-C 1m,19.90
```

For `viabilidade` analysis you can use a CSV with only the `Nome do Produto` column:

```
Nome do Produto
Fone de ouvido bluetooth
Cabo USB-C 1m
```

---

## 4) Small normalization helper (map scraper output to canonical keys)

Add this helper to `services/service.py` (or a new `core/normalize.py`) and apply it to each result before returning to the UI. This makes the front-end rendering stable.

```python
# example: services/normalize.py

CANONICAL_KEYS = [
    'Nome', 'Estado', 'Preço anunciado', 'Quantidade de vendas', 'Giro', 'Foto', 'Link do anuncio', 'Pesquisa',
    'nosso_preco', 'Preço sugerido', 'Desvio', 'diferenca_porcentagem', 'diferenca_reais'
]

KEY_ALIASES = {
    'Anuncio': 'Nome',
    'nome': 'Nome',
    'preco_anunciado': 'Preço anunciado',
    'preco': 'Preço anunciado',
    'vendas': 'Quantidade de vendas',
    'link': 'Link do anuncio'
}


def normalize_result(row: dict) -> dict:
    """Return a new dict using canonical keys and mapping known aliases."""
    normalized = {}
    for key in CANONICAL_KEYS:
        normalized[key] = None

    for k, v in row.items():
        if k in CANONICAL_KEYS:
            normalized[k] = v
        elif k in KEY_ALIASES:
            normalized[KEY_ALIASES[k]] = v
        else:
            # keep extras under their original key (optional)
            normalized[k] = v

    # Format 'Foto' as spreadsheet-friendly formula if it's present and not already
    if normalized.get('Foto') and isinstance(normalized['Foto'], str) and 'IMAGEM(' not in normalized['Foto']:
        normalized['Foto'] = f'=IMAGEM("{normalized["Foto"]}")'

    # Remove None values for cleaner JSON responses (optional)
    return {k: v for k, v in normalized.items() if v is not None}
```

Then, in service methods (e.g., `analisar_viabilidade`) map each result through `normalize_result` before returning.

Example usage inside `ShopeeMarketResearchService.analisar_viabilidade` after collecting `lista_final`:

```python
from services.normalize import normalize_result
return [normalize_result(r) for r in lista_final]
```

---

Commit message suggestion: "Add code snippets: app fix, cleaned requirements, sample CSV, normalize helper"

If you want I can open a branch and add these files to the repository and then request the draft issue to include references to these files. Tell me if you'd like me to push these changes directly to a branch and open a PR.
