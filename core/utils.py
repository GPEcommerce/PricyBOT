import time
import base64
import os

class Utils:

    SERVICE_COLUMNS = {
        "Pesquisa de Viabilidade": ["Nome"],
        "Analise Curva A": ["Nome"],
        "PMA": ["Nome", "Preço"],
        "Manutenção de Margem" : ["Nome", "Preço"],
    }

    @staticmethod
    def scroll_pagina(tab,
                      item_selector: str,
                      limite_itens: int = 60,
                      max_falhas_consecutivas: int = 2):
        """
        Rola a página com uma espera dinâmica e crescente por novos itens,
        parando ao atingir a meta de itens ou após falhas consecutivas.
        """
        print(f"Iniciando processo de scroll. Meta: ~{limite_itens} itens.")
        falhas_consecutivas = 0
        total_scrolls = 0

        while True:
            # Pega a contagem de itens antes de qualquer ação
            try:
                script_contagem = f"document.querySelectorAll('{item_selector}').length"
                contagem_antes = tab.call_method("Runtime.evaluate", expression=script_contagem, returnByValue=True).get("result", {}).get("value", 0)
            except Exception as e:
                print(f"Erro ao contar itens. Abortando scroll. Erro: {e}")
                break

            # --- VERIFICA CONDIÇÕES DE PARADA ---
            if contagem_antes >= limite_itens:
                print(f"Meta de {limite_itens} itens atingida (encontrados: {contagem_antes}). Parando o scroll.")
                break
            
            if falhas_consecutivas >= max_falhas_consecutivas:
                print(f"Nenhum item novo carregado nas últimas {max_falhas_consecutivas} tentativas. Considerado fim da página.")
                break

            # --- EXECUTA O SCROLL ---
            total_scrolls += 1
            print(f"Scroll #{total_scrolls}: Rolando página (itens atuais: {contagem_antes}).")
            script_scroll = "window.scrollBy(0, 1000);"
            tab.call_method("Runtime.evaluate", expression=script_scroll)

            # --- NOVA LÓGICA DE ESPERA DINÂMICA ---
            novos_itens_carregados = False
            tempo_de_espera_atual = 1.0  # Começa esperando 1 segundo
            max_tempo_espera = 5.0      # Máximo de 5 segundos
            incremento = 1.0            # Aumenta a espera em 1 segundo a cada falha na tentativa

            print("-> Iniciando espera dinâmica por novos itens...")
            while tempo_de_espera_atual <= max_tempo_espera:
                print(f"   Aguardando por {tempo_de_espera_atual:.1f}s...")
                time.sleep(tempo_de_espera_atual)
                
                try:
                    contagem_depois = tab.call_method("Runtime.evaluate", expression=script_contagem, returnByValue=True).get("result", {}).get("value", 0)
                except Exception:
                    contagem_depois = contagem_antes # Assume que falhou se não conseguiu contar

                if contagem_depois > contagem_antes:
                    print(f"   SUCESSO: Itens aumentaram de {contagem_antes} para {contagem_depois}.")
                    falhas_consecutivas = 0
                    novos_itens_carregados = True
                    break  # Sai do loop de espera dinâmica e vai para o próximo scroll
                else:
                    # Se não encontrou, aumenta o tempo de espera para a próxima tentativa dentro deste mesmo scroll
                    tempo_de_espera_atual += incremento
            
            # Avalia o resultado do ciclo de espera dinâmica
            if not novos_itens_carregados:
                print(f"-> FALHA NO SCROLL #{total_scrolls}: Nenhum item novo carregado após esperar até {max_tempo_espera:.1f}s.")
                falhas_consecutivas += 1

        print("Processo de scroll finalizado.")

    @staticmethod
    def wait_for_multiple_elements(tab, selectors: dict, timeout: int = 15) -> str:
        """
        Aguarda por um de vários seletores e retorna a chave do primeiro que for encontrado.
        """
        start_time = time.time()
        print(f"Aguardando por um dos seguintes estados: {list(selectors.keys())}")
        
        scripts = {key: f"!!document.querySelector('{selector}')" for key, selector in selectors.items()}

        while time.time() - start_time < timeout:
            for key, script in scripts.items():
                try:
                    result = tab.call_method("Runtime.evaluate", expression=script, returnByValue=True)
                    if result.get("result", {}).get("value") is True:
                        print(f"Estado detectado: '{key}'")
                        return key
                except Exception:
                    time.sleep(0.1)
            time.sleep(0.5)

        print("ERRO: Timeout ao esperar por um dos estados.")
        Utils.take_screenshot(tab, file_name_prefix='deteccao_estado_timeout')
        return 'timeout'

    @staticmethod
    def wait_for_either_element(tab, success_selector: str, failure_selector: str, other_selector: str = None, timeout: int = 15) -> str:
        """
        Aguarda por um de três elementos e retorna qual foi encontrado.
        """
        selectors = {
            'success': success_selector,
            'failure': failure_selector
        }
        if other_selector:
            selectors['other'] = other_selector
        
        return Utils.wait_for_multiple_elements(tab, selectors, timeout)
    
    @staticmethod
    def take_screenshot(tab, file_name_prefix='screenshot'):
        """
        Tira um print da tela da aba atual e salva como um arquivo .png.
        """
        try:
            output_dir = "debug_screenshots"
            os.makedirs(output_dir, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            file_path = os.path.join(output_dir, f"{file_name_prefix}_{timestamp}.png")

            print(f"DETALHE: Tirando um print da tela e salvando em: {file_path}")

            screenshot_data = tab.call_method("Page.captureScreenshot")
            
            image_data = base64.b64decode(screenshot_data['data'])
            with open(file_path, 'wb') as f:
                f.write(image_data)
            
            print("Print da tela salvo com sucesso.")
            
        except Exception as e:
            print(f"Falha ao tentar tirar o print da tela: {e}")
