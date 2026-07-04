from app.llm.caller import complete, stream
from app.llm.providers import PROVIDER_MODELS


class LLMService:
    complete = staticmethod(complete)
    stream = staticmethod(stream)
   
