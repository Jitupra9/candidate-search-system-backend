from pydantic import BaseModel ,Field
from typing import Optional

class Ask_api_base(BaseModel):
    quary:Optional[str] = Field(description="asked query")
    k:Optional[int] = Field(description="number of document retriver")