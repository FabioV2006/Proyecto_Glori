FROM node:22-bookworm-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY src/ src/
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt 'gunicorn>=23,<24'
COPY glori/ glori/
COPY --from=frontend /app/dist/ dist/
COPY scripts/iniciar-web.sh scripts/iniciar-web.sh
RUN useradd --system glori
USER glori
CMD ["sh", "scripts/iniciar-web.sh"]
