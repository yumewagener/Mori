FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e ".[all]"
COPY src/ ./src/
CMD ["python", "-m", "src.main"]
