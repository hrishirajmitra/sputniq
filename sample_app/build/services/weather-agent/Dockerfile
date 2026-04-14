
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV SERVICE_ID=weather-agent
ENV SERVICE_TYPE=agent

CMD ["python", "-m", "src.agents.weather"]

