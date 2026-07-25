"""Example pgm script.

Run it on its own:

    $ pgm hello_world
    {"greeting": "Hello, world!", "name": "world"}

Or give it a name through the pipe:

    $ echo '{"name": "Travis"}' | pgm hello_world
    {"greeting": "Hello, Travis!", "name": "Travis"}
"""


def run(data: dict) -> dict:
    """Greet whoever is named in the incoming record."""
    name = data.get("name") or "world"
    return {"name": name, "greeting": "Hello, %s!" % name}
