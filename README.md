# PyGoldberg-Machine

An opinionated framework for running modular building blocks of functionality,
each one a single Python file. `pgm` finds a script by name, feeds it data, and
prints what it returns — so scripts chain together with a plain shell pipe.

```console
$ pgm hello_world
{"greeting": "Hello, world!", "name": "world"}

$ echo '{"name": "Travis"}' | pgm hello_world
{"greeting": "Hello, Travis!", "name": "Travis"}
```

## Install

```console
$ poetry install      # development
$ pip install .       # or install the built wheel
```

Both give you the `pgm` command.

## Writing a script

A script is one Python file defining `run`:

```python
def run(data: dict) -> dict:
    return {"doubled": data["value"] * 2}
```

That is the whole contract. A script never reads stdin, never prints, and never
parses arguments — pgm owns both ends.

## Finding scripts

`pgm do_something` looks for `do_something.py` in this order, first match wins:

1. the current working directory
2. every directory in the `PGM_PATHS` environment variable (`:`-separated,
   searched left to right)
3. the `scripts/` directory shipped inside the `pgm` package

So a file in the directory you are standing in transparently shadows a packaged
one. `pgm --list` shows everything reachable, with shadowed entries marked `#`;
`pgm --where <name>` prints the file a name resolves to; `pgm --paths` prints
the search order.

## Input

pgm reads stdin and turns it into records, then calls `run` **once per record**.

| stdin | `run` receives |
| --- | --- |
| nothing | `{}`, once |
| `{"a": 1}` | `{"a": 1}` |
| one JSON object per line | each object, in turn |
| `[{"a": 1}, {"a": 2}]` | each element, in turn |
| a path to an existing file | the file's contents, parsed by these same rules |
| anything else | `{"value": "<the line>"}` |

The path rule is what makes big payloads cheap: a script can hand the next
stage a filename instead of the data, and the next stage cannot tell the
difference. Path references may chain (a file containing a path to a file), and
pgm stops with an error if the chain loops.

## Output

Whatever `run` returns is rendered to stdout:

| return type | printed as |
| --- | --- |
| `dict` | one JSON object on one line |
| `list` | one JSON string per element, one per line |
| `set` | one element per line, sorted, strings printed raw |
| `str` | printed directly — it must be a path that exists |
| `None` | nothing; the script is a sink |

Because a `list` prints one JSON object per line and stdin reads one record per
line, `pgm a | pgm b` fans out naturally: three records out of `a` means three
calls into `b`.

```console
$ pgm fan_out | pgm hello_world
{"greeting": "Hello, ada!", "name": "ada"}
{"greeting": "Hello, alan!", "name": "alan"}
{"greeting": "Hello, grace!", "name": "grace"}
```

## Errors

Failures print one line on stderr and exit non-zero — a missing script, a file
with no `run`, a `run` that cannot take a single dict, a raised exception, or a
return value pgm cannot print. Pass `--traceback` to see the full stack when a
script raises.

## Development

```console
$ poetry run pytest
```
