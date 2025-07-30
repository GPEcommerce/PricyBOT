import re
from core.exceptions import LoginRequiredException, EmailVerificationRequiredException
from core.utils import Utils
import requests
import cv2
import numpy as np
import json
from typing import List, Dict, Any, Callable
import time

class ShopeePesquisaMercado:
    """
    Classe responsável por realizar a automação de pesquisa de mercado na plataforma Shopee.
    """
    def __init__(self, tab):
        self.tab = tab
        self.orb = cv2.ORB_create(nfeatures=1000)
        self.features_referencia_cache = {}

    # --- Métodos de Lógica Interna e Helpers ---

    def _preparar_features_referencia(self, imagens_ref: List[str]) -> List[Any]:
        """Pré-calcula e armazena em cache os features das imagens de referência."""
        features_referencia = []
        if not imagens_ref:
            return features_referencia

        for path_img in imagens_ref:
            if path_img not in self.features_referencia_cache:
                try:
                    img_ref = cv2.imread(path_img, cv2.IMREAD_GRAYSCALE)
                    if img_ref is None: continue
                    kp, des = self.orb.detectAndCompute(img_ref, None)
                    if des is not None:
                        self.features_referencia_cache[path_img] = (kp, des)
                except Exception as e:
                    print(f"Não foi possível processar a imagem de referência {path_img}: {e}")
                    continue
            if path_img in self.features_referencia_cache:
                features_referencia.append(self.features_referencia_cache[path_img])
        return features_referencia

    def _imagem_e_semelhante_orb(self, url_imagem_produto: str, features_referencia: List[Any], limiar_matches: int) -> bool:
        """Compara a imagem de um produto com uma lista de features de referência."""
        if not url_imagem_produto or not features_referencia: return False
        try:
            resposta = requests.get(url_imagem_produto, timeout=10)
            resposta.raise_for_status()
            img_produto = cv2.imdecode(np.frombuffer(resposta.content, np.uint8), cv2.IMREAD_GRAYSCALE)
            if img_produto is None: return False
            kp_prod, des_prod = self.orb.detectAndCompute(img_produto, None)
            if des_prod is None: return False
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
            for _, des_ref in features_referencia:
                if des_ref is None: continue
                matches = bf.knnMatch(des_ref, des_prod, k=2)
                good_matches = [m for m, n in matches if m.distance < 0.75 * n.distance]
                if len(good_matches) >= limiar_matches:
                    return True
            return False
        except Exception as e:
            print(f"Erro ao comparar imagem com ORB {url_imagem_produto}: {e}")
            return False

    def _parse_preco(self, preco_str: str) -> float:
        """Converte string de preço para float. Ex: "R$ 45,99" -> 45.99"""
        if not preco_str: return 0.0
        try:
            # Remove o símbolo da moeda, pontos e substitui a vírgula
            cleaned_str = re.sub(r'[R$\s]', '', preco_str).replace('.', '').replace(',', '.')
            return float(cleaned_str)
        except (ValueError, TypeError):
            return 0.0

    def _extrair_numeros(self, texto: str) -> int:
        if not texto: return 0
        texto = texto.lower()
        match = re.search(r'([\d,\.]+)', texto)
        if not match: return 0
        
        qtd_str = match.group(1).replace('.', '').replace(',', '.')
        try:
            qtd = float(qtd_str)
            if 'mil' in texto or 'k' in texto:
                return int(qtd * 1000)
            return int(qtd)
        except (ValueError, TypeError):
            return 0

    def _processar_resultados(
        self,
        termo_pesquisa: str,
        filtro_callback: Callable[[Dict[str, Any]], Dict[str, Any] | None],
        imagens_ref: List[str] = None,
        limiar_matches: int = 12
    ) -> List[Dict[str, Any]]:
        """
        Função central refatorada para processar os resultados da busca.
        Recebe um 'callback' que contém a lógica específica de cada tipo de análise.
        """
        item_selector = 'li.shopee-search-item-result__item:has(div.line-clamp-2)'
        Utils.scroll_pagina(self.tab, item_selector=item_selector)
        features_referencia = self._preparar_features_referencia(imagens_ref)
        produtos_coletados = self.coletar_elementos()
        lista_final = []

        for produto_bruto in produtos_coletados:
            try:
                if features_referencia:
                    if not self._imagem_e_semelhante_orb(produto_bruto.get('imagem'), features_referencia, limiar_matches):
                        continue
                
                produto_processado = filtro_callback(produto_bruto)
                
                if produto_processado:
                    produto_processado["Pesquisa"] = termo_pesquisa
                    lista_final.append(produto_processado)
            except Exception as e:
                print(f"Erro ao processar produto: {produto_bruto.get('nome', 'N/A')}. Erro: {e}")
                continue
        
        return lista_final
    
    # --- Métodos Públicos (API da Classe) ---

    def realizar_busca(self, termo: str):
        """
        Preenche o campo de busca, executa a pesquisa e verifica de forma inteligente
        se o resultado foi a página de resultados esperada ou uma tela de login.
        """
        print(f"Realizando busca pelo termo: '{termo}'...")
        
        busca_script = f'''
        (function(){{
            var input = document.querySelector('input.shopee-searchbar-input__input');
            if (!input) return false;
            input.focus();
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, `{termo.replace('`', '')}`);
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            var btn = input.closest('form')?.querySelector('button[type="button"]');
            if (btn) {{ btn.click(); }}
            return true;
        }})();
        '''
        self.tab.call_method("Runtime.evaluate", expression=busca_script)

        # Sucesso: A lista de resultados. É um seletor bom.
        # Falha: O campo de input de login. É um sinal inequívoco da página de login.
        # Usamos a nova função aqui também para maior clareza
        status = Utils.wait_for_multiple_elements(
            tab=self.tab,
            selectors={
                'success': "ul.shopee-search-item-result__items",
                'failure': 'input[name="loginKey"]'
            }
        )

        if status == 'failure':
            Utils.take_screenshot(self.tab, file_name_prefix='busca_exigiu_login')
            raise LoginRequiredException("A Shopee redirecionou para a página de login durante a busca.")
        elif status == 'timeout':
            Utils.take_screenshot(self.tab, file_name_prefix='busca_timeout')
            raise Exception("A página de resultados da busca não carregou a tempo (timeout). Verifique o print salvo.")
        
        print("Busca realizada e página de resultados carregada com sucesso.")

    def coletar_elementos(self) -> List[Dict[str, Any]]:
        coleta_script = '''
        (function(){
        var produtos = [];
        var itens = document.querySelectorAll('li.shopee-search-item-result__item');

        itens.forEach(function(el){
            var vendidos = el.querySelector('div.mb-2.flex.items-center.space-x-1 > div.truncate.text-shopee-black87.text-xs.min-h-4')?.innerText || '';

            var giro = '';
            var xpathResult = document.evaluate(
                ".//div[contains(@class, 'wTool-search-result')]/p[3]/strong",
                el,
                null,
                XPathResult.FIRST_ORDERED_NODE_TYPE,
                null
            );
            if(xpathResult.singleNodeValue){
                giro = xpathResult.singleNodeValue.innerText.trim();
            }

            produtos.push({
                nome: el.querySelector('a.contents div.line-clamp-2')?.innerText || '',
                estado: el.querySelector('a.contents div.flex.items-center.space-x-1.max-w-full > div > span.align-middle')?.innerText || '',
                preco: el.querySelector('a.contents div > div > div:nth-child(2) > div.flex.items-center > div > span.font-medium.truncate')?.innerText || '',
                vendidos: vendidos,
                giro: giro,
                imagem: el.querySelector('a.contents img')?.src || '',
                link: el.querySelector('a.contents')?.href || ''
            });
        });
        return produtos;
        })();
        '''
        result = self.tab.call_method("Runtime.evaluate", expression=coleta_script, returnByValue=True)
        
        dados_brutos = result.get("result", {}).get("value", [])

        if not dados_brutos:
            print("AVISO: A coleta de elementos retornou uma lista vazia. Isso pode indicar que:")
            print("1. A página de resultados não continha produtos.")
            print("2. Os seletores de CSS dentro do script 'coleta_script' estão desatualizados.")
            Utils.take_screenshot(self.tab, file_name_prefix='coleta_vazia')
        
        return dados_brutos

    def fazer_login(self, usuario, senha):
        """
        Realiza o fluxo de login, priorizando a verificação de sucesso antes de
        checar por páginas de 2FA ou outros estados.
        """
        login_url = "https://shopee.com.br/buyer/login"
        print(f"Navegando para a página de login: {login_url}")
        self.tab.call_method("Page.navigate", url=login_url, _timeout=30)
        
        Utils.wait_for_multiple_elements(self.tab, {'campo_login': 'input[name="loginKey"]'}, timeout=15)
            
        print(f"Tentando fazer login com o usuário: {usuario}...")
        
        usuario_json = json.dumps(usuario)
        senha_json = json.dumps(senha)
        script_preenchimento = f'''
        (async function() {{
            function fillInput(selector, value) {{
                const input = document.querySelector(selector);
                if (!input) return;
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                nativeInputValueSetter.call(input, value);
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
            fillInput('input[name="loginKey"]', {usuario_json});
            fillInput('input[name="password"]', {senha_json});
            await new Promise(resolve => setTimeout(resolve, 500));
            const loginButton = document.querySelector('button.b5aVaf.PVSuiZ.Gqupku');
            if (loginButton) loginButton.click();
        }})();
        '''
        self.tab.call_method("Runtime.evaluate", expression=script_preenchimento, awaitPromise=True)
        print("Formulário de login submetido. Verificando resultado...")

        # --- ALTERAÇÃO DE FLUXO ---
        # Etapa 1: Verificar prioritariamente o sucesso do login (página principal carregada).
        # Um bom indicador de sucesso é a barra de pesquisa ou o nome de usuário.
        seletor_sucesso = 'input.shopee-searchbar-input__input, .navbar__username'
        print(f"Aguardando por indicador de sucesso ({seletor_sucesso}) por até 10s...")
        
        status_inicial = Utils.wait_for_multiple_elements(
            tab=self.tab,
            selectors={'success': seletor_sucesso},
            timeout=10  # Timeout mais curto para a verificação primária.
        )

        if status_inicial == 'success':
            print("✅ Login realizado com sucesso, página principal detectada.")
            return True

        # Etapa 2: Se o sucesso não foi detectado, verificar os outros possíveis estados.
        print("Página principal não detectada em 10s. Verificando outros estados (2FA, erro, captcha)...")

        seletor_botao_2fa_email = "div > div > div > div > div > div > button"
        possiveis_estados_secundarios = {
            'erro_credenciais': 'div.wS7x9S',
            'pagina_verificacao_2fa': seletor_botao_2fa_email,
            'captcha_visivel': 'div.shopee-modal__container',
        }

        status_secundario = Utils.wait_for_multiple_elements(
            tab=self.tab,
            selectors=possiveis_estados_secundarios,
            timeout=10  # Timeout para os estados secundários.
        )

        if status_secundario == 'erro_credenciais':
            Utils.take_screenshot(self.tab, file_name_prefix='login_falhou_credenciais')
            raise LoginRequiredException("Falha no login: usuário ou senha incorretos.")
            
        elif status_secundario == 'pagina_verificacao_2fa':
            print("Página de verificação (2FA) detectada.")
            Utils.take_screenshot(self.tab, file_name_prefix='login_verificacao_2fa')
            # --- ALTERAÇÃO: Apenas levanta a exceção, sem clicar no botão ---
            raise EmailVerificationRequiredException("Verificação por e-mail é necessária.")
            
        elif status_secundario == 'captcha_visivel' or status_secundario == 'timeout':
            Utils.take_screenshot(self.tab, file_name_prefix='login_captcha_ou_timeout')
            raise ConnectionError("Timeout ou CAPTCHA detectado após tentativa de login.")

        else:
            Utils.take_screenshot(self.tab, file_name_prefix='login_estado_desconhecido')
            raise Exception(f"Estado inesperado '{status_secundario}' após o login.")

    def gerar_analise_viabilidade(self, termo: str, imagens_ref: List[str] = None, limiar_matches: int = 12) -> List[Dict[str, Any]]:
        """Gera um relatório de viabilidade de produtos."""
        def filtro(produto: Dict[str, Any]) -> Dict[str, Any] | None:
            vendidos = self._extrair_numeros(produto.get('vendidos', ''))
            if vendidos < 5: return None
            return {
                "Anuncio": produto.get('nome', ''),
                "Preço anunciado": self._parse_preco(produto.get('preco')),
                "Estado": produto.get('estado', ''),
                "Quantidade de vendas": vendidos,
                "Giro": self._extrair_numeros(produto.get('giro', '')),
                "Foto": f'=IMAGEM("{produto.get("imagem", "")}")',
                "Link do anuncio": produto.get('link', '')
            }
        return self._processar_resultados(termo, filtro, imagens_ref, limiar_matches)

    def gerar_pma(self, termo: str, pma: float, imagens_ref: List[str] = None, limiar_matches: int = 12) -> List[Dict[str, Any]]:
        """Gera um relatório de Preço de Mercado Abaixo (PMA)."""
        def filtro(produto: Dict[str, Any]) -> Dict[str, Any] | None:
            preco_anunciado = self._parse_preco(produto['preco'])
            if preco_anunciado >= pma: return None
            desvio = round(((pma - preco_anunciado) / pma) * 100, 2) if pma != 0 else 0
            return {
                "Nome": produto['nome'], "Estado": produto['estado'], "Preço anunciado": preco_anunciado,
                "Preço sugerido" : pma, "Desvio": desvio,
                "Quantidade de vendas": self._extrair_numeros(produto['vendidos']),
                "Foto": f'=IMAGEM("{produto["imagem"]}")', "Link do anuncio": produto['link']
            }
        return self._processar_resultados(termo, filtro, imagens_ref, limiar_matches)

    def gerar_analise_manutencao_margem(self, termo: str, nosso_preco: float, imagens_ref: List[str] = None, limiar_matches: int = 12) -> List[Dict[str, Any]]:
        """Gera um relatório de Manutenção de Margem."""
        def filtro(produto: Dict[str, Any]) -> Dict[str, Any] | None:
            preco_anunciado = self._parse_preco(produto['preco'])
            if preco_anunciado >= nosso_preco: return None
            diferenca_porcentagem = round(((nosso_preco - preco_anunciado) / nosso_preco) * 100, 2) if nosso_preco != 0 else 0
            return {
                "nome": produto['nome'], "estado": produto['estado'], "preco_anunciado": preco_anunciado,
                "nosso_preco": nosso_preco, "diferenca_porcentagem": diferenca_porcentagem,
                "diferenca_reais": round(nosso_preco - preco_anunciado, 2),
                "vendas": self._extrair_numeros(produto['vendidos']),
                "Foto": f'=IMAGEM("{produto["imagem"]}")', "link": produto['link']
            }
        return self._processar_resultados(termo, filtro, imagens_ref, limiar_matches)
