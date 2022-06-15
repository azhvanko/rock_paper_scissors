SHELL = /bin/bash
WS_CONTAINER_NAME := battle_app
DB_CONTAINER_NAME := battle_postgres

.PHONY: run test

# docker
run:
	docker-compose up --build --remove-orphans

docker_rm_all:
	docker-compose down -v --rmi all

# shortcuts
ws_container:
	docker exec -it $(WS_CONTAINER_NAME) $(SHELL)

db_container:
	docker exec -it $(DB_CONTAINER_NAME) $(SHELL)

create_db_schema:
	docker exec -it $(WS_CONTAINER_NAME) $(SHELL) -c "python manage.py create_db_schema"

drop_db_schema:
	docker exec -it $(WS_CONTAINER_NAME) $(SHELL) -c "python manage.py drop_db_schema"

recreate_db_schema:
	docker exec -it $(WS_CONTAINER_NAME) $(SHELL) -c "python manage.py recreate_db_schema"

test:
	docker exec -it $(WS_CONTAINER_NAME) $(SHELL) -c "python -m pytest"
