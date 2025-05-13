#!/bin/bash

echo "Deteniendo contenedores actuales..."
docker-compose down

echo "Eliminando imagen API antigua..."
docker rmi extractor_api:latest || true

echo "Reconstruyendo imagen de Docker..."
docker-compose build --no-cache api

echo "Iniciando contenedores..."
docker-compose up -d

echo "Esperando a que los servicios se inicien..."
sleep 5

echo "Verificando logs del contenedor API..."
docker logs extractor_api

echo "Contenedores reconstruidos y ejecutándose. Comprueba los logs para asegurarte de que todo funciona correctamente." 