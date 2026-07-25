"""Example pgm script.

Run it on its own:

    $ pgm hello_world
    {"greeting": "Hello, world!", "name": "world"}

Give it a name through the pipe:

    $ echo '{"name": "Travis"}' | pgm hello_world
    {"greeting": "Hello, Travis!", "name": "Travis"}

Or an option of its own:

    $ pgm --shout hello_world
    {"greeting": "HELLO, WORLD!", "name": "world"}
"""


def run(args: dict, data: dict) -> dict:
    """Greet whoever is named in the incoming record."""
    name = data.get("name") or "world"
    greeting = "Hello, %s!" % name
    if args.get("shout"):
        greeting = greeting.upper()
    return {"name": name, "greeting": greeting}
