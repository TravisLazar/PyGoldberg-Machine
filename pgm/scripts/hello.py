"""Example pgm script, driven entirely by its options.

Run it on its own:

    $ pgm hello
    {"greeting": "Hello, Anonymous!", "name": "Anonymous"}

Give it a name:

    $ pgm --name=Travis hello
    {"greeting": "Hello, Travis!", "name": "Travis"}

Options combine:

    $ pgm --name=Travis --shout hello
    {"greeting": "HELLO, TRAVIS!", "name": "Travis"}
"""
from pgm import get_str, call, log


def run(args: dict, data: dict) -> dict:
    """Greet whoever is named in the incoming record."""
    name = get_str(args, "name", "Anonymous")

    greeting = f"Hello, {name}!"

    if args.get("shout"):
        greeting = greeting.upper()

    return {"name": name, "greeting": greeting}
