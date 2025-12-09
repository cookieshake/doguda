
from pydantic import BaseModel

from dogu import doguda


class PingResponse(BaseModel):
    markdown: str


@doguda
def ping(x: int) -> PingResponse:
    return PingResponse(markdown=f"ping {x}")
