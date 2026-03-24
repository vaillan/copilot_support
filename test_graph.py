from app.main import crear_grafo

def test_crear_grafo():
    try:
        app = crear_grafo()
        print("✅ Grafo creado exitosamente.")
        return True
    except Exception as e:
        print(f"❌ Error al crear el grafo: {e}")
        return False

if __name__ == "__main__":
    test_crear_grafo()
