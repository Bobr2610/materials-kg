FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY kg_engine ./kg_engine
COPY ui-page.html ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e . \
    && pip install --no-cache-dir "markitdown[docx,xlsx]"

EXPOSE 8090

CMD ["python", "kg_engine/scripts/run_materials_api.py"]
