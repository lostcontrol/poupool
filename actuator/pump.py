import asyncio
import logging

log = logging.getLogger("poupool.%s" % __name__)

class Pump(object):
    
    @asyncio.coroutine
    def start(self):
        log.info("Pump started")

    @asyncio.coroutine
    def stop(self):
        log.info("Pump stopped")

