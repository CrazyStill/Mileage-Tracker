FROM python:3.9-slim

# Install system dependencies for ARM
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    zlib1g-dev \
    libqt5gui5 libqt5widgets5 libqt5network5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy filtered requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app files
COPY . /app

EXPOSE 5000
ENV FLASK_APP=app.py

CMD ["flask", "run", "--host=0.0.0.0", "--port=80"]
