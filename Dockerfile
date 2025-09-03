# 1. Usar uma imagem base Python mais leve (slim)
FROM python:3.10-slim-bookworm

# 2. Instalar apenas as dependências mínimas para o Google Chrome Headless
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxkbcommon0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libpango-1.0-0 \
    libasound2 \
    fonts-liberation \
    libfontconfig1 \
    libgl1 \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# 3. Instala o chrome-headless-shell
RUN wget -q https://storage.googleapis.com/chrome-for-testing-public/139.0.7258.154/linux64/chrome-headless-shell-linux64.zip && \
    unzip chrome-headless-shell-linux64.zip && \
    mv chrome-headless-shell-linux64 /opt/ && \
    ln -s /opt/chrome-headless-shell-linux64/chrome-headless-shell /usr/local/bin/chrome-headless-shell && \
    rm chrome-headless-shell-linux64.zip

# 4. Cria diretório da aplicação
WORKDIR /app

# 5. Copia arquivos do projeto para o diretório de trabalho atual
COPY . .

# 6. Instala dependências Python
RUN pip install --no-cache-dir --upgrade pip && pip install -r requirements.txt

# 7. Expõe apenas a porta da API, já que não há mais VNC
EXPOSE 8000

# 8. Comando para rodar a API diretamente com Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]