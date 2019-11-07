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


async def main() -> None:
    client = await aiowamp.connect("", realm="")

    await client.register("io.giesela.add", add)
    await client.register("io.giesela.fibonacci", fibonacci)

    result = await client.call("io.giesela.add", 1, 3)
    assert result[0] == 4

    call = client.call("io.giesela.fibonacci", kwargs={"iterations": 50})
    async for progress in call:
        print(progress[0])

    final = await call
    print(final[0])


if __name__ == "__main__":
    asyncio.run(main())
