import asyncio
import logging

log = logging.getLogger("poupool.%s" % __name__)

class Pump(object):
    
    async def start(self):
        log.info("Pump started")

    async def stop(self):
        log.info("Pump stopped")

