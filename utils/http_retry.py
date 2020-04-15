# Retry operation if timeout
import asyncio
from requests.exceptions import HTTPError

async def http_retry(func, args=[], kwargs={}):
    for retry in range(3):
        try:
            return func(*args, **kwargs)
        except HTTPError as e:
            if "504" in str(e): await asyncio.sleep(1+retry)
            else: raise HTTPError
        else:
            break
    else:
        raise HTTPError
