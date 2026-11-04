FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY brain ./brain
COPY migrations ./migrations
RUN pip install --no-cache-dir -e ".[postgres]"
ENV PYDANTIC_AI_NO_BANNER=1
EXPOSE 8000
# Test environment: synthetic seed. Pilot and live: the API runs "brain migrate && brain serve" (see infra/).
CMD ["sh", "-c", "brain seed && brain serve --host 0.0.0.0 --port 8000"]
