FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

# Xvfb (가상 X11 디스플레이) + xclip (시스템 클립보드)
# SmartEditor ONE은 실제 Ctrl+V 붙여넣기만 허용 → X11 클립보드 필요
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    xclip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt

COPY . .

CMD ["xvfb-run", "-a", "python", "scheduler.py"]
