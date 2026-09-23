FROM alpine:3.20
RUN apk add --no-cache curl tzdata
COPY dynu-update.sh /usr/local/bin/dynu-update
RUN chmod +x /usr/local/bin/dynu-update
VOLUME /state
ENTRYPOINT ["/usr/local/bin/dynu-update"]
