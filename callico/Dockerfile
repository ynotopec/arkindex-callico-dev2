FROM node:20-alpine as frontend-build

WORKDIR /src
COPY ./front /src
RUN npm ci
RUN npm run production

FROM python:3.11-alpine

ENV FRONTEND_DIR /static/front

ADD requirements.txt tmp/requirements.txt
ADD requirements-docker.txt tmp/requirements-docker.txt
RUN apk update && \
  # Callico dependencies requirements
  apk add --virtual build gcc musl-dev && \
  # PostgreSQL
  apk add postgresql-dev && \
  # Install Callico Python dependencies
  pip install -r /tmp/requirements-docker.txt -r /tmp/requirements.txt && \
  # Cleanup
  apk del build && \
  rm -rf /tmp/build

# Copy Version file
COPY callico/VERSION /etc/callico.version

# Copy frontend static files
COPY --from=frontend-build /src/dist /static/front

# Install app source code
COPY . /tmp/build
RUN pip install -q /tmp/build && rm -rf /tmp/build

# Collect callico static files
RUN manage.py collectstatic --no-input

# Needed to use django-admin
ENV DJANGO_SETTINGS_MODULE=callico.base.settings

ENV PORT 80
EXPOSE 80

ENV PROMETHEUS_METRICS_PORT 3000
EXPOSE $PROMETHEUS_METRICS_PORT

CMD gunicorn --bind=0.0.0.0:80 --bind 0.0.0.0:$PROMETHEUS_METRICS_PORT --workers=4 callico.base.wsgi:application
