import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test requiring LLM API keys"
    )
