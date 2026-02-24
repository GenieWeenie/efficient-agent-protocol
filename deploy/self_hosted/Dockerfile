FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY . /app
RUN python -m pip install --upgrade pip \
    && pip install .

RUN useradd --create-home eap \
    && mkdir -p /var/lib/eap \
    && chown -R eap:eap /app /var/lib/eap

USER eap
