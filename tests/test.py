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
    await c.call("wamp.session.list")


asyncio.run(main())
