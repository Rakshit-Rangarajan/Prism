FROM node:22-alpine AS ui-build
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /service
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY demo ./demo
COPY scripts ./scripts
COPY --from=ui-build /build/frontend/dist ./frontend/dist
COPY tests ./tests
RUN python -m unittest discover -s demo -p 'test_*.py' -v && \
    python -m unittest discover -s tests -p 'test_*.py' -v
ENV PORT=10000
EXPOSE 10000
CMD ["sh","-c","exec uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-10000}"]
