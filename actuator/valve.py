import asyncio

class Valve(object):
    
    @asyncio.coroutine
    def open(self):
        print("Valve opened")

    @asyncio.coroutine
    def close(self):
        print("Valve closed")

