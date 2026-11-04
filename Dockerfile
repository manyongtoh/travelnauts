FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY brain ./brain
RUN pip install --no-cache-dir ".[postgres]"
ENV PYDANTIC_AI_NO_BANNER=1
EXPOSE 8000
CMD ["sh", "-c", "brain seed && brain serve --host 0.0.0.0 --port 8000"]
