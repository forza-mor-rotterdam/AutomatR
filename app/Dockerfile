FROM python:3.13.5-slim-bullseye

EXPOSE 5672

ENV APP_HOME=/app \
    APP_USER=appuser \
    APP_USER_ID=2000 \
    PYTHONUNBUFFERED=1

RUN groupadd -r "$APP_USER" && \
    useradd -r -u "$APP_USER_ID" -g "$APP_USER" -d "$APP_HOME" -s /sbin/nologin -c "Docker image user" "$APP_USER"

WORKDIR /app/

RUN apt-get update \
    && apt-get dist-upgrade -y \
    && apt-get autoremove -y \
    && apt-get install --no-install-recommends -y git

COPY . /app/

RUN chown -R "$APP_USER":"$APP_USER" "$APP_HOME" \
    && pip install --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

USER $APP_USER

ARG GIT_SHA
ENV GIT_SHA=$GIT_SHA
ARG DEPLOY_DATE
ENV DEPLOY_DATE=$DEPLOY_DATE

CMD ["python", "melding_afhandelen.py"]
