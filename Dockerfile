# Image for The Newsroom (Django news application).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System packages needed to build the MariaDB driver (mysqlclient).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential pkg-config libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Defaults that work with a plain `docker run`: SQLite inside the container
# and any host name allowed (so the Docker playground URL works).
# docker-compose.yml overrides DB_ENGINE to use MariaDB instead.
ENV DB_ENGINE=sqlite \
    DJANGO_ALLOWED_HOSTS=*

EXPOSE 8000

# Create/upgrade the tables, then start the development server.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
