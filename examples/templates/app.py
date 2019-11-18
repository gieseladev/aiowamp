import argparse
import asyncio
from typing import List

import aiowamp.templ

template = aiowamp.templ.Template(uri_prefix="std.math.")


# you can omit the uri for procedures. In that case, the uri will be the name
# of the function.
# Because our template has a prefix, in this case the final result will be
# "std.math.divide".
@template.procedure()
async def divide(a: float, b: float, *, integer: bool = False) -> float:
    if integer:
        return a // b
    else:
        return a / b


@template.procedure()
async def total_sum(*values: float, start: float = 0.) -> float:
    return sum(values, start)


@template.event("some.other.result")
async def on_result(event: aiowamp.SubscriptionEventABC, weights: List[int]) -> None:
    client = event.client
    total_weight, = await client.call("std.math.total_sum", *weights)

    average_weight, = await client.call("std.math.divide", total_weight, len(weights),
                                        kwargs={"integer": True})

    print("average weight:", average_weight)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="router url")
    parser.add_argument("--realm", help="router realm")

    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    client = await template.create_client(args.url, realm=args.realm)

    import random

    await client.publish("some.other.result", [random.randrange(500) for _ in range(10)],
                         exclude_me=False)

    await asyncio.sleep(5)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
