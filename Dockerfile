FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY backend/ backend/
COPY streaming/ streaming/
COPY digital_twin/ digital_twin/
COPY ml/ ml/
RUN pip install --no-cache-dir '.[kafka]'
COPY --from=frontend /web/dist frontend/dist
RUN mkdir -p data artifacts
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
