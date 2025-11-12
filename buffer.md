Automatiser en un script idempotant l'install :
```
git clone https://gitlab.teklia.com/callico/callico.git
cd callico
docker compose up
docker compose run callico django-admin migrate
docker compose run callico django-admin createsuperuser
```

Ajouter le script de uninstall
