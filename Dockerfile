# Use a stable, official Playwright image based on Ubuntu 22.04 LTS
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Define o diretório de trabalho
WORKDIR /app

# Copia os arquivos da aplicação
COPY . .

# Instala as dependências Python do seu projeto
RUN pip install --no-cache-dir -r requirements.txt

# Garante que os navegadores e suas dependências de sistema estejam instalados
RUN playwright install --with-deps

# Expõe a porta
EXPOSE 8000

# Comando para iniciar a aplicação
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]