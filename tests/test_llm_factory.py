import unittest
from unittest.mock import patch, MagicMock
from app.models.llm_factory import get_llm, _create_llm
from langchain_core.rate_limiters import InMemoryRateLimiter

class TestLLMFactory(unittest.TestCase):
    def setUp(self):
        get_llm.cache_clear()

    @patch('app.models.llm_factory.settings')
    @patch('app.models.llm_factory.init_chat_model')
    def test_get_llm_default(self, mock_init, mock_settings):
        mock_settings.LLM_PROVIDER = None
        mock_settings.LLM_MODEL = None
        mock_settings.LLM_API_KEY = "test_key"
        mock_settings.LLM_REQUESTS_PER_SECOND = 0.0
        
        get_llm()
        
        mock_init.assert_called_with(
            model="gemini-1.5-pro",
            model_provider="google_genai",
            temperature=0.0,
            api_key="test_key",
            max_retries=3,
            timeout=900
        )

    @patch('app.models.llm_factory.settings')
    @patch('app.models.llm_factory.init_chat_model')
    def test_get_llm_custom_provider(self, mock_init, mock_settings):
        mock_settings.LLM_PROVIDER = "openai"
        mock_settings.LLM_MODEL = "gpt-4"
        mock_settings.LLM_API_KEY = "openai_key"
        mock_settings.LLM_REQUESTS_PER_SECOND = 0.0
        
        get_llm(temperature=0.5)
        
        mock_init.assert_called_with(
            model="gpt-4",
            model_provider="openai",
            temperature=0.5,
            api_key="openai_key",
            max_retries=3,
            timeout=900
        )

    @patch('app.models.llm_factory.settings')
    @patch('app.models.llm_factory.init_chat_model')
    def test_get_llm_with_rate_limiter_init_chat_model(self, mock_init, mock_settings):
        mock_settings.LLM_PROVIDER = "openai"
        mock_settings.LLM_MODEL = "gpt-4"
        mock_settings.LLM_API_KEY = "openai_key"
        mock_settings.LLM_REQUESTS_PER_SECOND = 5.0
        mock_settings.LLM_CHECKS_PER_SECOND = 10.0
        
        get_llm()
        
        _, kwargs = mock_init.call_args
        self.assertIn("rate_limiter", kwargs)
        self.assertIsInstance(kwargs["rate_limiter"], InMemoryRateLimiter)

    @patch('app.models.llm_factory.settings')
    @patch('app.models.llm_factory.ChatOllama')
    def test_get_llm_with_rate_limiter_chat_ollama(self, mock_chat_ollama, mock_settings):
        mock_settings.LLM_PROVIDER = "local"
        mock_settings.LLM_MODEL = "llama3"
        mock_settings.LLM_API_KEY = ""
        mock_settings.LLM_REQUESTS_PER_SECOND = 2.0
        mock_settings.LLM_CHECKS_PER_SECOND = 5.0
        
        get_llm()
        
        mock_chat_ollama.assert_called_once()
        _, kwargs = mock_chat_ollama.call_args
        self.assertIn("rate_limiter", kwargs)
        self.assertIsInstance(kwargs["rate_limiter"], InMemoryRateLimiter)

if __name__ == '__main__':
    unittest.main()