FROM python:3.12-slim

WORKDIR /app

# System deps for asyncpg / bcrypt
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Copy all backend source
COPY . .

# Install dependencies and project
RUN pip install --no-cache-dir .

# Generate Prisma client
RUN prisma generate

EXPOSE 8000

CMD ["sh", "-c", "prisma db push && uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2"]
