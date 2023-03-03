FROM python:3

RUN pip install poetry

WORKDIR /app/

COPY pyproject.toml /app/pyproject.toml
COPY poetry.lock /app/poetry.lock
COPY README.md /app/README.md
COPY .flake8 /app/.flake8

COPY pybravia /app/pybravia

RUN /bin/true \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction \
    && rm -rf /root/.cache/pypoetry