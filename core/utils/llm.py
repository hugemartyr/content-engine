import os
from langchain_google_genai import ChatGoogleGenerativeAI
# Uncomment the imports below to use OpenAI or Anthropic
# from langchain_openai import ChatOpenAI
# from langchain_anthropic import ChatAnthropic
from core.settings import settings
from core.logging.logger import logger

def get_llm(temperature: float = 0.7, json_mode: bool = False):
    """
    Returns the configured LangChain ChatModel.
    Supports local Ollama models (via OpenAI-compatible API) or Gemini.
    """
    # -- Local Ollama Setup (One-Model Setup) --
    if settings.USE_LOCAL_LLM:
        from langchain_openai import ChatOpenAI
        model_name = settings.LOCAL_LLM_MODEL
        api_url = settings.LOCAL_LLM_URL
        
        extra_args = {}
        if json_mode:
            extra_args["response_format"] = {"type": "json_object"}
            
        logger.info(f"Initializing local Ollama LLM: {model_name} at {api_url}")
        return ChatOpenAI(
            model=model_name,
            openai_api_base=api_url,
            openai_api_key="ollama",  # required placeholder
            temperature=temperature,
            **extra_args
        )

    # -- OpenRouter (if configured) --
    if settings.OPENROUTER_API_KEY:
        from langchain_openai import ChatOpenAI
        # OpenRouter API uses the OpenAI compatible endpoint with a custom base URL.
        # Default model can be set via an environment variable or fallback to a common model.
        model_name = os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")
        api_url = "https://openrouter.ai/api/v1"
        extra_args = {}
        if json_mode:
            extra_args["response_format"] = {"type": "json_object"}
        logger.info(f"Initializing OpenRouter LLM: {model_name} at {api_url}")
        return ChatOpenAI(
            model=model_name,
            openai_api_base=api_url,
            openai_api_key=settings.OPENROUTER_API_KEY,
            temperature=temperature,
            **extra_args,
        )
    # -- Google Gemini (Default) --
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        # Check environment directly just in case pydantic didn't pick it up
        api_key = os.getenv("GEMINI_API_KEY")
        
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set. LLM calls will fail unless configured in .env.")
        
    # We use gemini-1.5-flash or gemini-2.5-flash as the actual model name in langchain-google-genai.
    # Note that langchain-google-genai supports model names like "gemini-1.5-flash"
    model_name = "gemini-3.5-flash"
    
    extra_args = {}
    if json_mode:
        # Some langchain integrations support structured output or json_mode
        # In langchain-google-genai, json mode is enabled by setting response_mime_type="application/json"
        extra_args["response_mime_type"] = "application/json"

    logger.info(f"Initializing Gemini LLM with temperature={temperature}")
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=temperature,
        **extra_args
    )

    # -- OpenAI Configuration (Comment out Gemini and uncomment below to use OpenAI) --
    # openai_api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    # if not openai_api_key:
    #     logger.warning("OPENAI_API_KEY is not set.")
    # model_name = "gpt-4o-mini"
    # extra_args = {}
    # if json_mode:
    #     extra_args["response_format"] = {"type": "json_object"}
    # logger.info(f"Initializing OpenAI LLM: {model_name} with temperature={temperature}")
    # return ChatOpenAI(
    #     model=model_name,
    #     openai_api_key=openai_api_key,
    #     temperature=temperature,
    #     **extra_args
    # )

    # -- Anthropic Configuration (Comment out Gemini and uncomment below to use Anthropic) --
    # anthropic_api_key = settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY")
    # if not anthropic_api_key:
    #     logger.warning("ANTHROPIC_API_KEY is not set.")
    # model_name = "claude-3-5-sonnet-20240620"
    # logger.info(f"Initializing Anthropic LLM: {model_name} with temperature={temperature}")
    # return ChatAnthropic(
    #     model=model_name,
    #     anthropic_api_key=anthropic_api_key,
    #     temperature=temperature
    # )
