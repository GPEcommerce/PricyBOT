import os
import pandas as pd
from fastapi.concurrency import run_in_threadpool

# Importações de negócio e automação
from core.chrome import Chrome
from plataforms.shopee.shopee_pesquisa_mercado import ShopeePesquisaMercado
from core.exceptions import LoginRequiredException, EmailVerificationRequiredException
from core.utils import Utils

def ler_arquivo(caminho_arquivo: str):
    """Lê um arquivo .xlsx ou .csv e retorna um DataFrame."""
    ext = os.path.splitext(caminho_arquivo)[1].lower()
    try:
        if ext == '.xlsx': return pd.read_excel(caminho_arquivo, engine='openpyxl')
        elif ext == '.csv':
            try: return pd.read_csv(caminho_arquivo, sep=',')
            except UnicodeDecodeError: return pd.read_csv(caminho_arquivo, sep=',', encoding='utf-8')
        else: raise ValueError("Formato de arquivo não suportado. Use .xlsx ou .csv.")
    except Exception as e:
        raise Exception(f"Erro ao ler o arquivo: {e}")

class ShopeeMarketResearchService:
    def __init__(self, browser: Chrome):
        self.navegador: Chrome = browser
        self.tab = None
        self.scraper = None

    async def _get_or_create_tab(self):
        """Cria uma nova aba no navegador se nenhuma estiver ativa."""
        if not self.tab:
            print("Nenhuma aba ativa. Criando uma nova...")
            self.tab = await run_in_threadpool(self.navegador.iniciar_navegador)
            self.scraper = ShopeePesquisaMercado(self.tab)

    async def _verificar_login_status(self):
        """Verifica se o usuário está logado na Shopee antes de prosseguir."""
        await self._get_or_create_tab()
        print("Verificando status de login na página inicial...")
        seletor_deslogado_universal = 'nav > ul > a:nth-child(6), input[name="loginKey"]'
        
        status = await run_in_threadpool(
            Utils.wait_for_either_element,
            self.tab,
            '.navbar__username',
            seletor_deslogado_universal,
            timeout=15
        )
        if status == 'failure':
            raise LoginRequiredException("Usuário não está logado na Shopee. Credenciais são necessárias.")
        elif status == 'timeout':
            await run_in_threadpool(Utils.take_screenshot, self.tab, 'erro_verificacao_inicial')
            raise ConnectionError("Não foi possível determinar o status de login na Shopee. Um print foi salvo.")
        print("Status: Usuário está LOGADO.")

    async def fazer_login(self, usuario, senha):
        """Executa o processo de login no scraper."""
        await self._get_or_create_tab()
        print("Iniciando o processo de login no scraper...")
        await run_in_threadpool(self.scraper.fazer_login, usuario, senha)
        print("Processo de login finalizado. Verificação de sucesso ocorrerá na próxima etapa.")

    async def _executar_pesquisa_em_lote(self, caminho_arquivo, colunas_necessarias, callback_scraper, *args):
        """Executa uma pesquisa para cada linha de um arquivo."""
        df = ler_arquivo(caminho_arquivo)
        for coluna in colunas_necessarias:
            if coluna not in df.columns:
                raise ValueError(f"O arquivo precisa conter a coluna '{coluna}'.")
        lista_produtos = df.to_dict('records')
        todos_resultados = []
        for produto in lista_produtos:
            await run_in_threadpool(self.scraper.realizar_busca, produto['Nome do Produto'])
            resultados_item = await run_in_threadpool(callback_scraper, produto, *args)
            todos_resultados.extend(resultados_item)
        return todos_resultados

    async def analisar_viabilidade(self, termo: str = None, caminho_arquivo: str = None, imagens_ref: list = None):
        """Inicia uma análise de viabilidade."""
        await self._verificar_login_status()
        if caminho_arquivo:
            def scraper_callback(produto, imgs_ref):
                return self.scraper.gerar_analise_viabilidade(produto['Nome do Produto'], imgs_ref)
            return await self._executar_pesquisa_em_lote(caminho_arquivo, ['Nome do Produto'], scraper_callback, imagens_ref)
        elif termo:
            # --- CORREÇÃO APLICADA ---
            # Passando 'termo' como argumento posicional para evitar confusão de dados.
            await run_in_threadpool(self.scraper.realizar_busca, termo)
            return await run_in_threadpool(self.scraper.gerar_analise_viabilidade, termo, imagens_ref)
        else:
            raise ValueError("Forneça um termo de busca ou um caminho de arquivo.")

    async def analisar_pma(self, termo: str = None, preco_maximo: float = None, caminho_arquivo: str = None, imagens_ref: list = None):
        """Inicia uma análise de PMA."""
        await self._verificar_login_status()
        if caminho_arquivo:
            def scraper_callback(produto, imgs_ref):
                return self.scraper.gerar_pma(produto['Nome do Produto'], float(produto['Preço do Produto']), imgs_ref)
            return await self._executar_pesquisa_em_lote(caminho_arquivo, ['Nome do Produto', 'Preço do Produto'], scraper_callback, imagens_ref)
        elif termo and preco_maximo is not None:
            # --- CORREÇÃO APLICADA ---
            await run_in_threadpool(self.scraper.realizar_busca, termo)
            return await run_in_threadpool(self.scraper.gerar_pma, termo, preco_maximo, imagens_ref)
        else:
            raise ValueError("Forneça um termo de busca e um preço, ou um caminho de arquivo.")

    async def analisar_manutencao_margem(self, termo: str = None, preco_nosso: float = None, caminho_arquivo: str = None, imagens_ref: list = None):
        """Inicia uma análise de manutenção de margem."""
        await self._verificar_login_status()
        if caminho_arquivo:
            def scraper_callback(produto, imgs_ref):
                return self.scraper.gerar_analise_manutencao_margem(produto['Nome do Produto'], float(produto['Preço do Produto']), imgs_ref)
            return await self._executar_pesquisa_em_lote(caminho_arquivo, ['Nome do Produto', 'Preço do Produto'], scraper_callback, imagens_ref)
        elif termo and preco_nosso is not None:
            # --- CORREÇÃO APLICADA ---
            await run_in_threadpool(self.scraper.realizar_busca, termo)
            return await run_in_threadpool(self.scraper.gerar_analise_manutencao_margem, termo, preco_nosso, imagens_ref)
        else:
            raise ValueError("Forneça um termo de busca e um preço, ou um caminho de arquivo.")

    async def retomar_e_verificar_aba(self):
        """Retoma o controle de uma aba existente e verifica se o login foi bem-sucedido."""
        if not self.navegador or not self.navegador.browser:
            raise ConnectionError("A instância do navegador não foi encontrada ou não está conectada.")
        
        # A chamada a list_tab() pode bloquear, então a colocamos em um threadpool
        tabs = await run_in_threadpool(self.navegador.browser.list_tab)
        if not tabs:
            raise ConnectionError("Nenhuma aba do navegador foi encontrada para retomar.")
        
        self.tab = tabs[-1]
        await run_in_threadpool(self.tab.start)
        self.scraper = ShopeePesquisaMercado(self.tab)
        
        print(f"Retomando o controle da aba ID: {self.tab.id}")
        print("Aguardando a confirmação do e-mail e o carregamento da página principal...")

        seletor_barra_pesquisa = 'input.shopee-searchbar-input__input'
        
        status = await run_in_threadpool(
            Utils.wait_for_multiple_elements,
            self.tab,
            {'success': seletor_barra_pesquisa},
            timeout=120  # Timeout longo para dar tempo ao usuário
        )
        
        if status != 'success':
            await run_in_threadpool(Utils.take_screenshot, self.tab, 'verificacao_email_falhou')
            raise ConnectionError("Não foi possível confirmar o login após a verificação de e-mail (a barra de pesquisa não apareceu).")
            
        print("✅ Confirmação de e-mail bem-sucedida. Página principal carregada. Prosseguindo com a pesquisa.")
        
    async def fechar(self):
        """Fecha a aba de pesquisa no navegador."""
        if self.navegador and self.tab:
            print(f"Fechando a aba da pesquisa (ID: {self.tab.id})...")
            await run_in_threadpool(self.navegador.fechar_navegador)
            self.tab = None
            print("Aba fechada. O navegador principal continua rodando.")
        else:
            print("Não há aba de pesquisa para fechar.")
