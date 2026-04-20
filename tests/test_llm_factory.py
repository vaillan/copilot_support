import unittest
from unittest.mock import patch, MagicMock
from app.models.llm_factory import get_llm

class TestLLMFactory(unittest.TestCase):
    @patch('app.models.llm_factory.settings')
    @patch('app.models.llm_factory.init_chat_model')
    def test_get_llm_default(self, mock_init, mock_settings):
        mock_settings.LLM_PROVIDER = None
        mock_settings.LLM_MODEL = None
        mock_settings.LLM_API_KEY = "test_key"
        
        get_llm()
        
        mock_init.assert_called_with(
            model="gemini-1.5-pro",
            model_provider="google_genai",
            temperature=0.0,
            api_key="test_key",
            max_retries=2,
            timeout=300
        )

    @patch('app.models.llm_factory.settings')
    @patch('app.models.llm_factory.init_chat_model')
    def test_get_llm_custom_provider(self, mock_init, mock_settings):
        mock_settings.LLM_PROVIDER = "openai"
        mock_settings.LLM_MODEL = "gpt-4"
        mock_settings.LLM_API_KEY = "openai_key"
        
        get_llm(temperature=0.5)
        
        mock_init.assert_called_with(
            model="gpt-4",
            model_provider="openai",
            temperature=0.5,
            api_key="openai_key",
            max_retries=2,
            timeout=300
        )

if __name__ == '__main__':
    unittest.main()
