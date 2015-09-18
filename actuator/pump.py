import asyncio

class Pump(object):
    
    @asyncio.coroutine
    def start(self):
        print("Pump started")

    @asyncio.coroutine
    def stop(self):
        print("Pump stopped")

