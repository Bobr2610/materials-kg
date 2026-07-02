FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY kg_engine ./kg_engine
COPY data ./data
COPY ui-page.html ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

RUN apt-get -o Acquire::Retries=3 update \
    && for attempt in 1 2 3; do \
        apt-get -o Acquire::Retries=3 install -y --fix-missing --no-install-recommends \
            tesseract-ocr fonts-dejavu-core && break; \
        if [ "$attempt" = 3 ]; then exit 1; fi; \
    done \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8090

CMD ["python", "kg_engine/scripts/run_materials_api.py"]
