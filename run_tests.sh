#!/bin/bash
# Script para ejecutar auditoría y pruebas dentro del entorno virtual
set -e

echo "Activando entorno virtual..."
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "No se encontró un entorno virtual (.venv o venv). Por favor, créalo primero."
    exit 1
fi

echo "Instalando/Actualizando dependencias..."
pip install -r requirements.txt

echo "Ejecutando linter (flake8)..."
flake8 app/ --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 app/ --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

echo "Ejecutando pruebas con pytest..."
pytest tests/ -v
