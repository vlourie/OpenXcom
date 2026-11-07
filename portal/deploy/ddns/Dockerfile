FROM python:3.12-alpine
RUN apk add --no-cache tzdata
COPY dynu_update.py /app/dynu_update.py
VOLUME /state
ENTRYPOINT ["python", "-u", "/app/dynu_update.py"]
