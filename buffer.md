Automatiser en un script idempotant l'installation et fournir la désinstallation :

* `install_callico.sh` prépare l'environnement Callico de bout en bout. Il clone ou met à jour le dépôt, lance l'orchestration Docker, applique les migrations et crée un super-utilisateur si nécessaire (en utilisant `DJANGO_SUPERUSER_*` ou en demandant le mot de passe).
* `uninstall_callico.sh` arrête les services Docker, supprime les volumes et efface le répertoire du projet.

Usage rapide :

```
./install_callico.sh [chemin/vers/dossier]
./uninstall_callico.sh [chemin/vers/dossier]
```
