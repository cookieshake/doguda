from pydantic import BaseModel


class UResponse(BaseModel):
    """Simple response model used in examples."""

    markdown: str
