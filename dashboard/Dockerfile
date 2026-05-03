FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /dashboard

COPY requirements.txt /dashboard/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py /dashboard/app.py

EXPOSE 8501

CMD ["streamlit", "run", "/dashboard/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
