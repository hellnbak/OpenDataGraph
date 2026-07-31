FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 --retries 10 -r requirements.txt
COPY . .
RUN useradd --uid 10001 --create-home opendatagraph \
    && mkdir -p /var/lib/opendatagraph/evidence \
    && chown -R opendatagraph:opendatagraph /app /var/lib/opendatagraph
USER 10001
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
