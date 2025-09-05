import subprocess
import os
import socket
import platform
import time
import random

def esperar_chrome_pronto(host='127.0.0.1', port=9222, timeout=45):
    """
    Aguarda o Chrome ficar pronto para aceitar conexões na porta de depuração.
    """
    print(f"Aguardando Chrome responder na porta {port}...")
    inicio = time.time()
    while time.time() - inicio < timeout:
        # Usamos um novo socket a cada tentativa para evitar problemas de estado
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1) # Timeout curto para cada tentativa de conexão
            try:
                if sock.connect_ex((host, port)) == 0:
                    print(f"✅ Chrome está pronto para conexões na porta {port}.")
                    return True
            except Exception:
                # Ignora falhas de conexão temporárias
                pass 
            time.sleep(0.5)
    print(f"❌ Timeout: Chrome não respondeu na porta {port} após {timeout} segundos.")
    return False

def iniciar_chrome(headless=False):
    """
    Inicia um processo do Chrome com depuração remota.
    - No Windows: Roda o Chrome instalado localmente (visível ou headless).
    - No Linux (Docker): Roda o Chrome instalado no container (sempre headless).
    """
    sistema = platform.system()
    comando = []
    user_data_dir = os.path.join(os.getcwd(), "chrome_temp_profile")
    
    # --- LÓGICA PARA WINDOWS (DESENVOLVIMENTO LOCAL) ---
    if sistema == "Windows":
        import winreg
        print("💻 Detectado ambiente Windows (desenvolvimento local).")
        def encontrar_caminho_chrome_windows():
            chaves_registro = [
                r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe",
                r"SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe",
            ]
            for chave in chaves_registro:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chave) as reg_key:
                        caminho, _ = winreg.QueryValueEx(reg_key, "")
                        return caminho
                except FileNotFoundError:
                    continue
            return None

        caminho_chrome = encontrar_caminho_chrome_windows()
        if not caminho_chrome:
            raise FileNotFoundError("Chrome.exe não encontrado no registro do Windows.")
        
        comando = [
            caminho_chrome,
            f"--remote-debugging-port=9222",
            f"--user-data-dir={user_data_dir}",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1366,768",
        ]
        # Adiciona o modo headless apenas se solicitado
        if headless:
            comando.append("--headless=new")
            
    # --- LÓGICA PARA LINUX (AMBIENTE DOCKER) ---
    else:
        print("🐳 Detectado ambiente Linux (Docker). Usando Chrome completo com Xvfb.")
        # O caminho para o Chrome completo instalado via apt-get
        caminho_chrome = "/usr/bin/google-chrome-stable" 
        
        # Sorteia uma resolução de tela comum para evitar fingerprinting
        resolucoes_comuns = ["1920,1080", "1366,768", "1440,900", "1536,864"]
        resolucao_escolhida = random.choice(resolucoes_comuns)
        print(f"🖥️ Usando resolução de tela: {resolucao_escolhida}")

        comando = [
            caminho_chrome,
            f"--remote-debugging-port=9222",
            f"--user-data-dir={user_data_dir}",
            # Flags para parecer mais 'humano' e evitar detecção
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--disable-blink-features=AutomationControlled", # Essencial!
            "--start-maximized", # Inicia maximizado na tela virtual
            # Flags técnicas para rodar bem no Docker
            "--no-sandbox", # Pode ser necessário dependendo da configuração
            "--disable-dev-shm-usage",
            "--disable-gpu", # Não há GPU no Xvfb
            f"--window-size={resolucao_escolhida}",
        ]

    try:
        print(f"▶️ Executando comando: {' '.join(comando)}")
        # A variável de ambiente DISPLAY=:1 (definida no entrypoint.sh)
        # direcionará a UI do Chrome para o Xvfb.
        processo = subprocess.Popen(comando)
        print(f"Processo do Chrome iniciado (PID: {processo.pid}).")
        return processo
    except FileNotFoundError:
        print(f"❌ ERRO: O executável do Chrome não foi encontrado em '{comando[0]}'.")
        return None
    except Exception as e:
        print(f"❌ ERRO ao tentar iniciar o processo do Chrome: {e}")
        return None

if __name__ == "__main__":
    print("Iniciando o Chrome localmente para teste...")
    # Ao executar o script diretamente, ele usará a lógica para o seu SO atual.
    processo_chrome = iniciar_chrome(headless=False) 
    if processo_chrome:
        print(f"Chrome iniciado com PID: {processo_chrome.pid}. Pressione Ctrl+C para encerrar.")
        try:
            processo_chrome.wait()
        except KeyboardInterrupt:
            print("\nEncerrando o processo do Chrome...")
            processo_chrome.terminate()
            print("Processo encerrado.")