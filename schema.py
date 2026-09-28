from pydantic import BaseModel
from typing import Any, Dict

class RetellFunctionCall(BaseModel):
    name: str
    call: Dict[str, Any] = {}
    args: Dict[str, Any] = {}