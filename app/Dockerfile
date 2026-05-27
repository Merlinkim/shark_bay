FROM python:3.12-slim
WORKDIR /srv

COPY app/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

COPY app /srv/app
COPY strategies /srv/strategies
COPY tests /srv/tests
COPY requirements-dev.txt /srv/requirements-dev.txt

CMD ["python", "-m", "app.main"]

FROM python:3.12-slim AS dev
WORKDIR /srv

COPY app/requirements.txt /srv/requirements.txt
COPY requirements-dev.txt /srv/requirements-dev.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt -r /srv/requirements-dev.txt

COPY app /srv/app
COPY strategies /srv/strategies
COPY tests /srv/tests
