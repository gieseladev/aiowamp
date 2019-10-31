import asyncio
import logging
import os
import sys

import aiowamp


async def main():
    # just a dirty little test to see how things are doing. Don't mind me.

    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    ser = aiowamp.serializers.JSONSerializer()
    conn = await aiowamp.transports.raw_socket.connect(os.getenv("WAMP_URI"), ser)
    # conn = await aiowamp.transports.web_socket.connect(os.getenv("WAMP_WS_URI"), ser)

    await conn.send(aiowamp.msg.Hello(
        aiowamp.URI(os.getenv("WAMP_REALM")), {
            "roles": {
                "publisher": {
                    "features": {
                        "publisher_exclusion": True
                    }
                }
            }
        }))
    await conn.recv()

    await asyncio.sleep(5)

    await conn.close()


asyncio.run(main())
