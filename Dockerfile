FROM python:3.10-slim
WORKDIR /app

ENV PYTHONPATH=/app   
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_ROOT_USER_ACTION=ignore

# System dependencies for numpy / scipy / arch (modern Debian compatible)
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    gfortran \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --default-timeout=300 -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]