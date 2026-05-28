FROM python:3.12-slim
WORKDIR /srv
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ /srv/app
COPY strategies/ /srv/strategies/
CMD ["python", "-m", "app.main"]
