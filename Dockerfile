# Text-to-SQL assistant — application image.
# Mock mode (the default) needs no GPU and downloads no models, so this image
# stays slim: it installs only the core requirements. To run with real bge-m3
# embeddings, also install requirements-embeddings.txt (set INSTALL_EMBEDDINGS=true).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/srv \
    CHROMA_PATH=/data/chroma

WORKDIR /srv

# psycopg2-binary ships manylinux wheels, so no compiler/libpq-dev is required.
COPY requirements.txt requirements-embeddings.txt ./
ARG INSTALL_EMBEDDINGS=false
RUN pip install -r requirements.txt && \
    if [ "$INSTALL_EMBEDDINGS" = "true" ]; then pip install -r requirements-embeddings.txt; fi

COPY app ./app
COPY chainlit.md ./chainlit.md

RUN mkdir -p /data/chroma

EXPOSE 8000

# --headless: do not try to open a browser inside the container.
CMD ["chainlit", "run", "app/chainlit_app.py", "--host", "0.0.0.0", "--port", "8000", "--headless"]
