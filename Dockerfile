FROM python:3.12-slim

WORKDIR /app

# Dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
# web (Flask) + ia (Gemini/Groq) + conflito (psycopg2/rapidfuzz — usado pela
# rota /conflitos-interesse). requirements-conflito puxa folha e o núcleo.
COPY requirements.txt requirements-web.txt requirements-ia.txt requirements-folha.txt requirements-conflito.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt -r requirements-ia.txt -r requirements-conflito.txt

# Copiar código
COPY . .

# Criar diretório do banco de dados
RUN mkdir -p /data

# Porta
EXPOSE 8080

# Entrypoint
CMD ["python", "web_app.py"]
