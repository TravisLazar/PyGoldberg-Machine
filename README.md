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
    return {"doubled": data["number"] * 2}
```

That is the whole contract. A script never reads stdin, never prints, and never
parses arguments — pgm owns both ends. It takes a dict and returns a dict, a
list of dicts, or the path of a file it wrote.

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
| anything else | an error |

That last row is the whole point. There is no guessing and no wrapping: a line
that is not a JSON object, an array of them, or a path to a readable file is
input pgm refuses rather than input pgm invents a shape for. Bare scalars
(`41`, `true`, `"hello"`), loose text, and directories are all errors.

The path rule is what makes big payloads cheap: a script can hand the next
stage a filename instead of the data, and the next stage cannot tell the
difference. A path may be bare or a quoted JSON string, may appear inside an
array alongside objects, and may chain (a file containing a path to a file);
pgm stops with an error if the chain loops.

## Output

Whatever `run` returns is rendered to stdout, under the same narrow contract:

| return type | printed as |
| --- | --- |
| `dict` | one JSON object on one line |
| `list` | one element per line — each element a JSON object, or a quoted path that exists |
| `str` | printed directly — one line, and it must be a path to a file that exists |
| anything else | an error |

Only two things ever travel a pgm pipe: a JSON object and a reference to a file
holding JSON objects. So every return value must be exactly JSON or exactly a
path, and every other return is a bug pgm reports instead of printing. `None`,
`42`, a `set`, a `tuple`, a `Path` object, a `NaN` buried in a dict, a string
that names nothing on disk — all errors. Scripts that exist only for their side
effects return the file they wrote, or `{}`.

Because a `list` prints one record per line and stdin reads one record per
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
with no `run`, a `run` that cannot take a single dict, a raised exception, input
pgm will not read, or a return value pgm will not print. Pass `--traceback` to
see the full stack when a script raises.

## Development

```console
$ poetry run pytest
```
