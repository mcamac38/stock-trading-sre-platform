FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY SRE_Stock_Sim_Current.py .

EXPOSE 8000

ENV APP_VERSION=v1

CMD ["python", "SRE_Stock_Sim_Current.py"]