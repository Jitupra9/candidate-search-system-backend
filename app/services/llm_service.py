from app.llm.caller import complete, stream, list_models
from app.llm.providers import PROVIDER_MODELS


class LLMService:
    complete = staticmethod(complete)
    stream = staticmethod(stream)
    list_models = staticmethod(list_models)
