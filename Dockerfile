FROM python:3.10

# Define variáveis de ambiente
ENV DISPLAY=:1

# Atualiza pacotes e instala dependências
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    gnupg \
    software-properties-common \
    fonts-liberation \
    libgbm1 \
    xdg-utils \
    libgtk-3-0 \
    libx11-xcb1 \
    libdbus-glib-1-2 \
    libnss3 \
    libasound2 \
    libxss1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libu2f-udev \
    libvulkan1 \
    xauth \
    xvfb \
    x11vnc \
    fluxbox \
    supervisor \
    python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Instala o Google Chrome
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get update && \
    apt-get install -y ./google-chrome-stable_current_amd64.deb && \
    rm google-chrome-stable_current_amd64.deb

# Instala o noVNC
RUN git clone https://github.com/novnc/noVNC.git /opt/novnc && \
    git clone https://github.com/novnc/websockify /opt/novnc/utils/websockify && \
    chmod +x /opt/novnc/utils/novnc_proxy

# Cria diretório da aplicação
WORKDIR /app

# Copia arquivos do projeto
COPY . /app

# Instala dependências Python
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia config do supervisord
COPY fastapi.conf /etc/supervisor/conf.d/fastapi.conf

# Expõe portas
EXPOSE 8000 6079

# Comando para rodar tudo com supervisord
CMD ["/usr/bin/supervisord", "-n"]
