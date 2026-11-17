FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
COPY sql ./sql
RUN pip install --no-cache-dir .
COPY static ./static
EXPOSE 8000
CMD ["uvicorn", "ziwei.api:app", "--host", "0.0.0.0", "--port", "8000"]
