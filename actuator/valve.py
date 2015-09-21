import asyncio
import logging

log = logging.getLogger("poupool.%s" % __name__)

class Valve(object):
    
    @asyncio.coroutine
    def open(self):
        log.info("Valve opened")

    @asyncio.coroutine
    def close(self):
        log.info("Valve closed")

