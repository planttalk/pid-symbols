# Stage 1: Build React/Vite frontend
FROM node:20-slim AS frontend-builder

WORKDIR /build/editor
COPY editor/package.json editor/package-lock.json ./
RUN npm ci --quiet
COPY editor/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim

WORKDIR /app

# System dependencies:
#   cairosvg  → libcairo2, libpango, libgdk-pixbuf, libffi, shared-mime-info
#   opencv    → libgl1, libglib2.0-0 (headless, no display needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        shared-mime-info \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (core app)
RUN pip install --no-cache-dir \
        cairosvg \
        albumentations \
        numpy \
        "opencv-python-headless" \
        Pillow

# Python dependencies (FastAPI collaborative API)
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# Application source
COPY . .

# Overlay with freshly built frontend (overrides any stale local dist/)
COPY --from=frontend-builder /build/editor/dist editor/dist

# Create runtime directories so volumes mount cleanly
RUN mkdir -p /app/processed /app/input /app/augmented /app/data

EXPOSE 43070 8000
