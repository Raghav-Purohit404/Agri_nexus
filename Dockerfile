FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN useradd --create-home --uid 10001 farmtwin
COPY pyproject.toml requirements.txt README.md ./
COPY farm_twin ./farm_twin
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN python -m pip install --no-cache-dir -r requirements.txt
USER farmtwin
EXPOSE 8000 8501
