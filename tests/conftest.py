# Archivo de configuración para pytest
import os
import sys

# Añadir el directorio raíz al path para que las pruebas puedan importar el paquete app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
