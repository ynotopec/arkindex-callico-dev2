```
== automated install ==
./install.sh --domain example.com --email admin@example.com [--admin-password <password>]

This script will:
- start the docker compose stack in ./callico
- apply database migrations
- ensure a Django superuser exists (username defaults to admin)
- configure a Caddy reverse proxy with Let's Encrypt TLS certificates

== uninstall ==
./uninstall.sh

== manual install ==
cd callico
docker compose up
docker compose run callico django-admin migrate
docker compose run callico django-admin createsuperuser
```
