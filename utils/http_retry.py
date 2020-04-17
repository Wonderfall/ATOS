# Retry operation if timeout
# Also asynchronize operation
import asyncio
from requests.exceptions import HTTPError
from utils.asynchronize import async_wrap

async def http_retry(func, args=[], kwargs={}):
    for retry in range(3):
        try:
            return await (async_wrap(func))(*args, **kwargs)
        except HTTPError as e:
            if "504" in str(e):
                await asyncio.sleep(1+retry)
            else:
                raise
    else:
        raise HTTPError(f"Tried '{func.__name__}' several times without success")