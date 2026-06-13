FROM python:3.12-slim

WORKDIR /app

# Dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY requirements-web.txt requirements-ia.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt -r requirements-ia.txt

# Copiar código
COPY . .

# Criar diretório do banco de dados
RUN mkdir -p /data

# Porta
EXPOSE 8080

# Entrypoint
CMD ["python", "web_app.py"]
