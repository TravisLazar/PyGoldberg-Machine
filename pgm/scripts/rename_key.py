"""Rename one key in every record: --from=old --to=new."""

from pgm import get_str


def run(args: dict, data: dict) -> list:
    from_key = get_str(args, "from") 
    to_key = get_str(args, "to") 

    data[to_key] = data.pop(from_key)

    return data