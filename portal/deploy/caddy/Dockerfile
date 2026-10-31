# Caddy with the Dynu DNS module: the certificate is proven through Dynu's API (DNS-01), so neither
# port 80 nor 443 is needed and the site can live on any port of a machine whose 80/443 are taken.
# caddy-dns/dynu v1 needs Caddy 2.10+, which caddy:2 is.
FROM caddy:2-builder AS build
RUN xcaddy build --with github.com/caddy-dns/dynu

FROM caddy:2
COPY --from=build /usr/bin/caddy /usr/bin/caddy
