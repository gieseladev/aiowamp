import argparse
import asyncio
from typing import AsyncIterator

import aiowamp


async def add(invocation: aiowamp.InvocationABC) -> int:
    # invocation[key] is short for either invocation.args[key] or
    # invocations.kwargs[key] depending on whether key is an index (int) or a
    # keyword (str).
    return invocation[0] + invocation[1]


async def fibonacci(invocation: aiowamp.InvocationABC) -> AsyncIterator[int]:
    # invocation.get is the same as dict.get but like invocation[key] works for
    # both args and kwargs.
    iterations = invocation.get("iterations", 10)

    a, b = 0, 1
    for i in range(iterations):
        yield a
        a, b = b, a + b


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="router url")
    parser.add_argument("--realm", help="router realm")

    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    print("connecting to", args.url)
    client = await aiowamp.connect(args.url, realm=args.realm)

    print("registering procedures")
    await client.register("io.giesela.add", add)
    await client.register("io.giesela.fibonacci", fibonacci)

    print("performing heavy addition")
    result = await client.call("io.giesela.add", 1, 3)
    assert result[0] == 4
    print(f"1 + 3 = {result[0]}")

    print("calculating 50th iteration of the fibonacci sequence")
    # notice that we didn't specify receive_progress=True here.
    # aiowamp automatically sets it when you do anything to indicate that you
    # want to receive progress results (like iterating over it or adding
    # on_progress handler).
    # This doesn't work if you explicitly disable it, or try to do it after the
    # message was sent.
    call = client.call("io.giesela.fibonacci", kwargs={"iterations": 50})
    i = 1
    async for progress in call:
        print(f"iteration {i}:", progress[0])
        i += 1

    final = await call
    print("iteration 50:", final[0])

    print("closing down")
    await client.close()

    print("closed")


if __name__ == "__main__":
    asyncio.run(main())
