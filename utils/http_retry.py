# Retry operation if timeout
# Also asynchronize operation
import asyncio
from achallonge import ChallongeException

async def async_http_retry(func, *args, **kwargs):
    for retry in range(3):
        try:
            return await func(*args, **kwargs)
        except ChallongeException as e:
            if "504" in str(e):
                await asyncio.sleep(1+retry)
            else:
                raise
        except asyncio.exceptions.TimeoutError:
            continue
    else:
        raise ChallongeException(f"Tried '{func.__name__}' several times without success")