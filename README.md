```
== automated install ==
./install.sh --domain example.com --email admin@example.com [--admin-password <password>]

This script will:
- start the docker compose stack in ./callico
- apply database migrations
- ensure a Django superuser exists (the identifier defaults to `admin` and is applied to the project's `USERNAME_FIELD`)
- configure a Caddy reverse proxy with Let's Encrypt TLS certificates and host-wide HTTP/HTTPS listeners (override with `--proxy-http-port` / `--proxy-https-port` if ports 80/443 are unavailable)

== uninstall ==
./uninstall.sh

== manual install ==
cd callico
docker compose up
docker compose run callico django-admin migrate
docker compose run callico django-admin createsuperuser
```
