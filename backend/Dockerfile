FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download OPIR safety model during build to ensure fast container startup
RUN python -c "from gliclass import GLiClassModel; from transformers import AutoTokenizer; GLiClassModel.from_pretrained('knowledgator/opir-multitask-multilang-v1.0'); AutoTokenizer.from_pretrained('knowledgator/opir-multitask-multilang-v1.0')"

# Copy application source code
COPY . /app

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
