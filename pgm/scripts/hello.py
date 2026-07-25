"""Example pgm script: the record says who, the options say how.

Greet whoever the record names:

    $ echo '{"firstname": "Ada", "lastname": "Lovelace"}' | pgm hello
    {"greeting": "Hello, Ada Lovelace!", "name": "Ada Lovelace"}

Either half on its own is enough, and --shout is the script's own option:

    $ echo '{"firstname": "Ada"}' | pgm --shout hello
    {"greeting": "HELLO, ADA!", "name": "Ada"}

With nothing to go on it still greets somebody:

    $ pgm hello
    {"greeting": "Hello, Anonymous!", "name": "Anonymous"}
"""

from pgm import get_str


def run(args: dict, data: dict) -> dict:
    """Greet whoever the record names."""
    firstname = get_str(data, "firstname", "", cast_numbers=True)
    lastname = get_str(data, "lastname", "", cast_numbers=True)

    name = " ".join(part for part in (firstname, lastname) if part) or "Anonymous"

    greeting = f"Hello, {name}!"

    if args.get("shout"):
        greeting = greeting.upper()

    return {"name": name, "greeting": greeting}
