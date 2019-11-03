import asyncio
import logging
import os
import sys

import aiowamp


async def main():
    # just a dirty little test to see how things are doing. Don't mind me.

    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    c = await aiowamp.connect(os.getenv("WAMP_URI"), realm=os.getenv("WAMP_REALM"))
    call = c.call("wamp.session.list")

    async for progress in call:
        print("GOT PROGRESS", progress)

    print("FINAL", await call)

    await asyncio.sleep(.1)
    await c.close()

    print(repr(c.session.goodbye))


asyncio.run(main())
