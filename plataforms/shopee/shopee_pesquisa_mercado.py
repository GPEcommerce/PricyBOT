# Arquivo: shopee_pesquisa_mercado.py (VERSÃO ADAPTADA)

import re
import time
import random
import cv2
import numpy as np
import requests
from urllib.parse import quote
from typing import List, Dict, Any, Callable
import threading # NOVO: Importado para gerenciar a espera assíncrona dos dados

from core.exceptions import LoginRequiredException, EmailVerificationRequiredException
from core.utils import Utils

class ShopeePesquisaMercado:
    """
    Classe responsável por realizar a automação de pesquisa de mercado na plataforma Shopee,
    utilizando a interceptação de API para coleta de dados.
    """
    def __init__(self, tab):
        self.tab = tab
        self.orb = cv2.ORB_create(nfeatures=1000)
        self.features_referencia_cache = {}
        
        # --- NOVO: Atributos para gerenciar a interceptação ---
        self.dados_api_busca = None
        self.evento_busca_concluida = threading.Event()

    # --- Métodos de Lógica Interna e Helpers ---

    # Os métodos _preparar_features_referencia e _imagem_e_semelhante_orb permanecem os mesmos
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
            # NOVO: Adiciona User-Agent para simular um navegador real
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            resposta = requests.get(url_imagem_produto, timeout=10, headers=headers)
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

    def _type_like_human(self, selector: str, text: str):
        """
        Método auxiliar para digitar texto em um campo de forma a simular um humano.
        """
        focus_script = f"document.querySelector('{selector}').focus();"
        self.tab.call_method("Runtime.evaluate", expression=focus_script)
        time.sleep(random.uniform(0.2, 0.5))
        for char in text:
            self.tab.call_method("Input.dispatchKeyEvent", type="char", text=char)
            time.sleep(random.uniform(0.06, 0.18))
            
    def _callback_carregamento_finalizado(self, **kwargs):
        """
        Função que será chamada quando uma requisição de rede for COMPLETAMENTE finalizada.
        """
        request_id = kwargs.get("requestId")
        try:
            response_data = self.tab.call_method("Network.getResponseBody", requestId=request_id)
            body = response_data.get('body', '{}')
            
            if '"items":' in body and '"total_count":' in body:
                print(f"✅ API de busca finalizada e corpo da resposta obtido para requestId: {request_id}")
                self.dados_api_busca = body
                self.evento_busca_concluida.set()

        except Exception:
            pass
    
    def _remove_listener_compat(self, event_name, cb):
        # Tenta nomes conhecidos
        for name in ("remove_listener", "del_listener"):
            func = getattr(self.tab, name, None)
            if callable(func):
                try:
                    func(event_name, cb)
                    return
                except TypeError:
                    pass
                except Exception:
                    pass
        # Fallback: se existir, limpa todos
        clean = getattr(self.tab, "clear_listeners", None)
        if callable(clean):
            try:
                clean()
            except Exception:
                pass

    def _interceptar_e_processar_busca(self) -> list:
        self.evento_busca_concluida.clear()
        self.dados_api_busca = None

        self.tab.set_listener("Network.loadingFinished", self._callback_carregamento_finalizado)
        self.tab.call_method("Network.enable")
        print("🔎 Monitoramento de rede ativado. Aguardando a finalização da chamada da API...")

        try:
            evento_ocorreu = self.evento_busca_concluida.wait(timeout=45)
            if not evento_ocorreu:
                Utils.take_screenshot(self.tab, 'api_busca_timeout')
                raise TimeoutError("Timeout: A API de busca da Shopee não respondeu a tempo.")

            if not self.dados_api_busca:
                raise Exception("A API de busca foi interceptada, mas não foi possível extrair os dados.")
        finally:
            # Garante limpeza mesmo em erro
            self.tab.call_method("Network.disable")
            self._remove_listener_compat("Network.loadingFinished", self._callback_carregamento_finalizado)

        import json
        dados_json = json.loads(self.dados_api_busca)
        produtos_brutos = dados_json.get("items", [])
        if not produtos_brutos:
            print("AVISO: API retornou uma lista de itens vazia.")
        return produtos_brutos
    
    def _processar_resultados(
        self,
        termo_pesquisa: str,
        filtro_callback: Callable[[Dict[str, Any]], Dict[str, Any] | None],
        imagens_ref: List[str] = None,
        limiar_matches: int = 12
    ) -> List[Dict[str, Any]]:
        produtos_coletados_api = self._interceptar_e_processar_busca()

        features_referencia = self._preparar_features_referencia(imagens_ref)
        lista_final = []

        for produto_bruto in produtos_coletados_api:
            try:
                # A estrutura do item da API é diferente, então acessamos 'item_basic'
                item_basic = produto_bruto.get('item_basic', {})
                if not item_basic: continue

                # ALTERADO: Constrói a URL da imagem a partir do ID
                imagem_id = item_basic.get('image')
                url_imagem = f"https://cf.shopee.com.br/file/{imagem_id}_tn" if imagem_id else ""
                
                if features_referencia:
                    if not self._imagem_e_semelhante_orb(url_imagem, features_referencia, limiar_matches):
                        continue
                
                # O filtro_callback agora recebe o item_basic da API
                produto_processado = filtro_callback(item_basic)
                
                if produto_processado:
                    produto_processado["Pesquisa"] = termo_pesquisa
                    lista_final.append(produto_processado)

            except Exception as e:
                print(f"Erro ao processar produto da API: {item_basic.get('name', 'N/A')}. Erro: {e}")
                continue
        
        return lista_final

    # --- Métodos Públicos (API da Classe) ---
    
    def realizar_busca(self, termo: str):
        print(f"Iniciando busca por '{termo}'. Estratégia primária: Interação com a UI.")
        seletor_barra_pesquisa = 'input.shopee-searchbar-input__input'
        status_barra = Utils.wait_for_multiple_elements(self.tab, {'barra_encontrada': seletor_barra_pesquisa}, timeout=5)
        if status_barra == 'barra_encontrada':
            print("Barra de pesquisa encontrada. Realizando busca via digitação...")
            try:
                self._type_like_human(seletor_barra_pesquisa, termo)
                time.sleep(random.uniform(0.3, 0.7))
                seletor_botao_busca = 'button.shopee-searchbar__search-button'
                script_clique = f"document.querySelector('{seletor_botao_busca}').click();"
                self.tab.call_method("Runtime.evaluate", expression=script_clique)
                print("Busca via UI submetida.")
            except Exception as e:
                print(f"ERRO ao tentar busca via UI: {e}. Acionando fallback para URL direta.")
                self._realizar_busca_por_url(termo)
        else:
            print("AVISO: Barra de pesquisa não encontrada em 5 segundos.")
            self._realizar_busca_por_url(termo)

    def _realizar_busca_por_url(self, termo: str):
        print("Acionando fallback: busca direta por URL.")
        termo_formatado = quote(termo)
        url_pesquisa = f"https://shopee.com.br/search?keyword={termo_formatado}"
        print(f"Navegando para: {url_pesquisa}")
        self.tab.call_method("Page.navigate", url=url_pesquisa, _timeout=30)

    def fazer_login(self, usuario, senha):
        """
        Realiza o fluxo de login, priorizando a verificação de sucesso antes de
        checar por páginas de 2FA ou outros estados.
        """
        login_url = "https://shopee.com.br/buyer/login"
        print(f"Navegando para a página de login: {login_url}")
        self.tab.call_method("Page.navigate", url=login_url, _timeout=30)
        
        Utils.wait_for_multiple_elements(self.tab, {'campo_login': 'input[name="loginKey"]'}, timeout=15)
        time.sleep(random.uniform(1.0, 2.0))    
        print(f"Tentando fazer login com o usuário: {usuario}...")
        self._type_like_human('input[name="loginKey"]', usuario)
        self._type_like_human('input[name="password"]', senha)
        time.sleep(random.uniform(0.5, 1.2))
        script_clique_login = "document.querySelector('button.b5aVaf.PVSuiZ.Gqupku').click();"
        self.tab.call_method("Runtime.evaluate", expression=script_clique_login)
        print("Formulário de login submetido. Verificando resultado...")

        seletor_sucesso = 'input.shopee-searchbar-input__input, .navbar__username'
        print(f"Aguardando por indicador de sucesso ({seletor_sucesso}) por até 10s...")
        
        status_inicial = Utils.wait_for_multiple_elements(
            tab=self.tab,
            selectors={'success': seletor_sucesso},
            timeout=10
        )

        if status_inicial == 'success':
            print("✅ Login realizado com sucesso, página principal detectada.")
            return True

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
            timeout=10
        )

        if status_secundario == 'erro_credenciais':
            Utils.take_screenshot(self.tab, file_name_prefix='login_falhou_credenciais')
            raise LoginRequiredException("Falha no login: usuário ou senha incorretos.")
            
        elif status_secundario == 'pagina_verificacao_2fa':
            print("Página de verificação (2FA) detectada. Solicitando envio do e-mail...")
            Utils.take_screenshot(self.tab, file_name_prefix='login_verificacao_2fa')
            
            script_clique_email = f"document.querySelector('{seletor_botao_2fa_email}').click();"
            try:
                self.tab.call_method("Runtime.evaluate", expression=script_clique_email)
                print("Comando para enviar e-mail de verificação foi enviado.")
            except Exception as e:
                print(f"AVISO: Não foi possível clicar no botão de envio de e-mail: {e}")

            raise EmailVerificationRequiredException("Verificação por e-mail é necessária.")
            
        elif status_secundario == 'captcha_visivel' or status_secundario == 'timeout':
            Utils.take_screenshot(self.tab, file_name_prefix='login_captcha_ou_timeout')
            raise ConnectionError("Timeout ou CAPTCHA detectado após tentativa de login.")

        else:
            Utils.take_screenshot(self.tab, file_name_prefix='login_estado_desconhecido')
            raise Exception(f"Estado inesperado '{status_secundario}' após o login.")
    
    def gerar_analise_viabilidade(self, termo: str, imagens_ref: List[str] = None, limiar_matches: int = 12) -> List[Dict[str, Any]]:
        """Gera um relatório de viabilidade de produtos."""
        def filtro(item_basic: Dict[str, Any]) -> Dict[str, Any] | None:
            giro = item_basic.get('sold', 0)
            if giro < 5: return None
            
            # Constrói o link do produto a partir dos IDs
            shop_id = item_basic.get('shopid', '')
            item_id = item_basic.get('itemid', '')
            link_produto = f"https://shopee.com.br/product/{shop_id}/{item_id}"
            imagem_id = item_basic.get('image')
            url_imagem = f"https://cf.shopee.com.br/file/{imagem_id}" if imagem_id else ""

            return {
                "Anuncio": item_basic.get('name', ''),
                # Preço na API vem como um inteiro (ex: 4599), dividimos para ter o valor real
                "Preço anunciado": item_basic.get('price', 0) / 100000,
                "Estado": item_basic.get('shop_location', ''),
                "Quantidade de vendas": item_basic.get('historical_sold', ''),
                "Giro": giro, # A API de busca não fornece essa informação diretamente
                "Foto": f'=IMAGEM("{url_imagem}")',
                "Link do anuncio": link_produto
            }
        return self._processar_resultados(termo, filtro, imagens_ref, limiar_matches)

    def gerar_pma(self, termo: str, pma: float, imagens_ref: List[str] = None, limiar_matches: int = 12) -> List[Dict[str, Any]]:
        """Gera um relatório de Preço de Mercado Abaixo (PMA)."""
        def filtro(item_basic: Dict[str, Any]) -> Dict[str, Any] | None:
            preco_anunciado = item_basic.get('price', 0) / 100000
            if preco_anunciado >= pma: return None
            desvio = round(((pma - preco_anunciado) / pma) * 100, 2) if pma != 0 else 0
            
            shop_id = item_basic.get('shopid', '')
            item_id = item_basic.get('itemid', '')
            link_produto = f"https://shopee.com.br/product/{shop_id}/{item_id}"
            imagem_id = item_basic.get('image')
            url_imagem = f"https://cf.shopee.com.br/file/{imagem_id}" if imagem_id else ""
            
            return {
                "Nome": item_basic.get('name', ''), "Estado": item_basic.get('shop_location', ''), 
                "Preço anunciado": preco_anunciado,
                "Preço sugerido" : pma, "Desvio": desvio,
                "Quantidade de vendas": item_basic.get('sold', 0),
                "Foto": f'=IMAGEM("{url_imagem}")', "Link do anuncio": link_produto
            }
        return self._processar_resultados(termo, filtro, imagens_ref, limiar_matches)

    def gerar_analise_manutencao_margem(self, termo: str, nosso_preco: float, imagens_ref: List[str] = None, limiar_matches: int = 12) -> List[Dict[str, Any]]:
        """Gera um relatório de Manutenção de Margem."""
        def filtro(item_basic: Dict[str, Any]) -> Dict[str, Any] | None:
            preco_anunciado = item_basic.get('price', 0) / 100000
            if preco_anunciado >= nosso_preco: return None
            diferenca_porcentagem = round(((nosso_preco - preco_anunciado) / nosso_preco) * 100, 2) if nosso_preco != 0 else 0
            
            shop_id = item_basic.get('shopid', '')
            item_id = item_basic.get('itemid', '')
            link_produto = f"https://shopee.com.br/product/{shop_id}/{item_id}"
            imagem_id = item_basic.get('image')
            url_imagem = f"https://cf.shopee.com.br/file/{imagem_id}" if imagem_id else ""

            return {
                "nome": item_basic.get('name', ''), "estado": item_basic.get('shop_location', ''), 
                "preco_anunciado": preco_anunciado,
                "nosso_preco": nosso_preco, "diferenca_porcentagem": diferenca_porcentagem,
                "diferenca_reais": round(nosso_preco - preco_anunciado, 2),
                "vendas": item_basic.get('sold', 0),
                "Foto": f'=IMAGEM("{url_imagem}")', "link": link_produto
            }
        return self._processar_resultados(termo, filtro, imagens_ref, limiar_matches)