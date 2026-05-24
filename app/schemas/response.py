from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    ok: bool
    message: str
    data: Optional[T] = None

    @classmethod
    def success(cls, data: Any = None, message: str = "Success") -> "ApiResponse":
        return cls(ok=True, message=message, data=data)

    @classmethod
    def error(cls, message: str = "Something went wrong") -> "ApiResponse":
        return cls(ok=False, message=message, data=None)