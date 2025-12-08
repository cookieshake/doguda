
from dogu import doguda, UResponse

@doguda
def ping(x: int) -> UResponse:
    return UResponse(markdown=f"ping {x}")
