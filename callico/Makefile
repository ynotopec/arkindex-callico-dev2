.PHONY: release antora antora-clean

generate-translations:
	callico/manage.py makemessages -l fr --no-location

compile-translations:
	callico/manage.py compilemessages

worker:
	celery -A callico.base worker -B -l INFO

antora:
	npx antora antora-playbook.yml

antora-clean:
	npx antora antora-playbook.yml --clean --fetch

release:
	@$(eval version:=$(shell cat callico/VERSION))
	@echo Releasing version $(version)
	git commit callico/VERSION -m "Version $(version)" --allow-empty
	git tag $(version)
	git push origin master $(version)
