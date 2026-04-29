FROM python:3.12-slim

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Tesseract OCR + Hebrew language pack
    tesseract-ocr \
    tesseract-ocr-heb \
    # Poppler (pdf2image / PyMuPDF fallback)
    poppler-utils \
    # WeasyPrint / Pango / Cairo (HTML → PDF)
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    # Fonts for Hebrew rendering
    fonts-dejavu-core \
    fonts-liberation \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# ── Python package ────────────────────────────────────────────────────────────
WORKDIR /app
COPY requirements-docker.txt .
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements-docker.txt

COPY . .

# ── Tesseract path ────────────────────────────────────────────────────────────
ENV TESSERACT_CMD=/usr/bin/tesseract

# ── Entrypoint ────────────────────────────────────────────────────────────────
ENTRYPOINT ["python", "cli.py"]
CMD ["--help"]
