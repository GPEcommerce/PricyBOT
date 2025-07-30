import os
import pychrome
import requests

class Chrome:
    def __init__(self):
        self.browser = None
        self.tab = None
        
    def connect(self):
        """
        Conecta-se a um navegador já em execução e VERIFICA ativamente a conexão.
        """
        is_in_docker = os.environ.get("RUNNING_IN_DOCKER", "false").lower() == "true"
        # Se no Docker (via docker-compose), o host é o nome do serviço.
        # Caso contrário, usa o localhost.
        host ="127.0.0.1"
        port = 9222
        
        connection_url = f"http://{host}:{port}"
        print(f"Tentando conectar ao navegador via: {connection_url}")
        
        try:
            self.browser = pychrome.Browser(url=connection_url)
            
            # --- NOVA VERIFICAÇÃO ROBUSTA ---
            # Apenas criar o objeto não é suficiente. Vamos testar a conexão
            # com um comando real para garantir que ela está pronta.
            print("Objeto Browser criado. Verificando a conexão real...")
            self.browser.list_tab() # Este comando falhará se a conexão não estiver 100% pronta.
            print("Conexão estabelecida e verificada com sucesso.")
            # --- FIM DA VERIFICAÇÃO ---

        except requests.exceptions.ConnectionError as e:
            print(f"ERRO DE CONEXÃO: Não foi possível conectar ao navegador em {connection_url}.")
            print("Verifique se o navegador de depuração está em execução e se não há um firewall bloqueando a porta 9222.")
            raise ConnectionError(f"Falha ao conectar no navegador: {e}")

    def iniciar_navegador(self):
        """ Inicia uma nova aba no navegador já conectado. """
        if not self.browser:
            raise Exception("A conexão com o navegador não foi estabelecida. Chame o método connect() primeiro.")
        
        print("Iniciando nova aba...")
        # A chamada new_tab() sem URL abre uma aba em branco ("about:blank"), que é mais estável.
        self.tab = self.browser.new_tab()
        self.tab.start()
        
        # Agora, com a aba já criada, navegamos para a página alvo.
        url_alvo = "https://shopee.com.br"
        print(f"Navegando para: {url_alvo}...")
        self.tab.call_method("Page.navigate", url=url_alvo, _timeout=30)
        print("Comando de navegação enviado com sucesso.")

        return self.tab

    def fechar_navegador(self):
        """ Fecha a aba específica que foi aberta pelo script. """
        if self.tab:
            print(f"Fechando a aba com ID: {self.tab.id}...")
            try:
                self.browser.close_tab(self.tab)
                self.tab = None
                print("Aba fechada com sucesso.")
            except pychrome.exceptions.CallMethodException as e:
                print(f"Aviso: erro ao fechar a aba (provavelmente já estava fechada): {e}")

