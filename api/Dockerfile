FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/kweli
WORKDIR /app

# DejaVu covers the accents in names (e.g. Ngũgĩ) that the built-in PDF fonts can't.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-nodeps.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir --no-deps -r requirements-nodeps.txt

COPY alembic.ini .
COPY migrations migrations
COPY api api
COPY paypal paypal
COPY proof proof
COPY audit audit
COPY vault vault
COPY agent agent
COPY packs packs
COPY scripts scripts

RUN useradd --system --create-home kweli
USER kweli

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
