.PHONY: backend-install backend-dev frontend-install frontend-dev test migrate init-mysql clear-cache docker-up

backend-install:
	python -m pip install -r backend/requirements-dev.txt

backend-dev:
	PYTHONPATH=backend python backend/run.py

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

test:
	PYTHONPATH=backend python -m pytest backend/tests
	cd frontend && npm run test

migrate:
	bash backend/scripts/migrate.sh

init-mysql:
	bash backend/scripts/init_mysql.sh

clear-cache:
	PYTHONPATH=backend python backend/scripts/clear_cache.py

docker-up:
	docker compose up --build
