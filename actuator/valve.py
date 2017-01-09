import asyncio
import logging

log = logging.getLogger("poupool.%s" % __name__)

class Valve(object):
    
    async def open(self):
        log.info("Valve opened")

    async def close(self):
        log.info("Valve closed")

