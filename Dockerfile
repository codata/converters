# CDIF Multi-Format Converters API & Studio
#
#   docker build -t cdif-converters .
#   docker run --rm -p 8000:8000 cdif-converters
#   open http://localhost:8000/docs
#

FROM python:3.12-slim-trixie AS runtime

ENV PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies if any needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-api.txt

# Copy converter repository code and submodules
COPY . /app

RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

CMD ["sh", "-c", "exec uvicorn cdif_converter.api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
