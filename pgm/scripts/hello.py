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


def run(args: dict, data: dict) -> dict:
    """Greet whoever is named in the incoming record."""
    name = args.get("name") or "Anonymous"

    greeting = "Hello, %s!" % name

    if args.get("shout"):
        greeting = greeting.upper()

    return {"name": name, "greeting": greeting}
