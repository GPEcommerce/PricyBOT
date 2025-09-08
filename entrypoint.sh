#!/bin/bash
# Inicia o Xvfb (display virtual) na tela :1 em segundo plano
Xvfb :1 -screen 0 1366x768x16 &

# Exporta a variável DISPLAY para que o Chrome e outras apps gráficas a utilizem
export DISPLAY=:1

# Inicia a sua aplicação FastAPI.
exec uvicorn app:app --host 0.0.0.0 --port 8000