# PyGoldberg-Machine

An opinionated framework for running modular building blocks of functionality,
each one a single Python file. `pgm` finds a script by name, feeds it data, and
prints what it returns — so scripts chain together with a plain shell pipe.

```console
$ pgm hello
{"greeting": "Hello, Anonymous!", "name": "Anonymous"}

$ echo '{"firstname": "Ada", "lastname": "Lovelace"}' | pgm --shout hello
{"greeting": "HELLO, ADA LOVELACE!", "name": "Ada Lovelace"}

$ pgm --count=3 --end=9 randint
{"value": 0}
{"value": 8}
{"value": 7}
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
def run(args: dict, data: dict) -> dict:
    factor = args.get("factor", 2)
    return {"scaled": data["number"] * factor}
```

That is the whole contract. `args` is what the command line asked for, `data` is
one record of input. A script never reads stdin, never prints, and never parses
arguments — pgm owns both ends. It returns a dict, a list of dicts, or the path
of a file it wrote.

A script that cannot answer until it has seen everything — a histogram, a total,
a sort — defines `run_all` instead:

```python
def run_all(args: dict, records: list) -> dict:
    return {"total": sum(record["number"] for record in records)}
```

Which one a script defines is the script's own business, not something the
command line has to remember, so `pgm numbers | pgm total` needs no flag and
cannot be got wrong. Defining both is an error. The two differ only in what
arrives:

| | `run` | `run_all` |
| --- | --- | --- |
| called | once per record | once, with the list |
| no input at all | once, with `{}` | once, with `[]` |
| returns | a dict, a list of dicts, or a path | the same |

Because both return the same things, `run_all` also fans back out: a sort takes
every record and gives back a list, and the next script sees them one at a
time again.

## Helpers

A script gets two dicts and no stdout of its own, so pgm covers both ends of
that. Along with `call` below, this is everything a script imports:

```python
from pgm import get_float, get_int, get_str, log


def run(args: dict, data: dict) -> dict:
    factor = get_float(args, "factor", 2.0)
    log("scaling by", factor)
    return {"value": data["value"] * factor}
```

`get_int`, `get_float` and `get_str` each read one option and insist on its
type, so no script has to write those checks again:

| call | result |
| --- | --- |
| `get_int(args, "count", 100)` | the option, or `100` if it was not given |
| `get_int(args, "count")` | the option — **required**, an error when missing |
| `get_float(args, "rate", 1.0)` | whole numbers widen: `--rate=2` gives `2.0` |
| `get_str(args, "logpath", "")` | text only; `--logpath=42` is an error |
| `get_str(args, "port", "", cast_numbers=True)` | text, but `--port=8080` gives `"8080"` |

A bad option reads like pgm's own errors — one plain line, because a mistyped
option is the user's business, not a script blowing up:

```console
$ pgm --count=lots randint
pgm: --count must be a whole number, got 'lots'
```

Booleans are turned away too, `cast_numbers` or not: `--count` with no value
parses to `true`, and `True` is an `int` as far as Python is concerned, so a
forgotten value never slips through as `1` or `"True"`. A default is handed back
untouched — it is the script's own value, not something the user typed. And
since these take a plain dict, they read `data` as happily as `args`.

`log` writes one line to **stderr**, tagged with the name of the script that
said it. stdout carries records and nothing else, so a `print` would land in the
next script's input as junk; `log` is the way to say anything to the person
running the pipeline:

```console
$ pgm --count=3 --end=9 randint | pgm double
double: scaling by 1.5
double: scaling by 1.5
double: scaling by 1.5
{"value": 13.5}
{"value": 1.5}
{"value": 9.0}

$ pgm --count=3 --end=9 randint | pgm double 2>/dev/null
{"value": 13.5}
{"value": 1.5}
{"value": 9.0}
```

## Chaining

A pipeline does not have to go through a shell. `call` runs another script and
hands back its records:

```python
from pgm import call, get_int, log


def run(args: dict, data: dict) -> list:
    rolls = get_int(args, "rolls", 2)
    log("rolling", rolls, "dice")
    numbers = call("randint", count=rolls, start=1, end=6)
    return [{"roll": record["value"]} for record in numbers]
```

```console
$ pgm --rolls=5 dice
dice: rolling 5 dice
{"roll": 4}
{"roll": 4}
{"roll": 6}
{"roll": 4}
{"roll": 3}
```

`call(script, data=None, **options)` is the whole of it, and it means exactly
what the command line means:

| call | command line |
| --- | --- |
| `call("randint", count=3)` | `pgm --count=3 randint` |
| `call("double", record)` | one record piped into `pgm double` |
| `call("double", records)` | many records — `run` is called once per record |
| `call("total", records)` | many records — a `run_all` script gets them all |
| `call("double", call("randint"))` | `pgm randint \| pgm double` |

Records go out through the same rendering a pipe uses and come back through the
same parsing, so **a script cannot tell whether it was called or piped**, and
there is only one set of rules to learn. That also means the answer is always a
list of records, however the other script phrased its return — a dict is one
record, a list is flattened, and a returned file path is read back off disk.
Take `[0]` when you know there is exactly one:

```python
greeting = call("hello", {"firstname": "Ada"}, shout=True)[0]
```

The script name is resolved the same way the command line resolves it, so a
local file shadows a packaged one here too. Options are keywords, and a script
whose option is named `script` or `data` is fine — those are positional. A
script that raises names itself in the error, whichever script called it, and
scripts that call each other in a circle are stopped with a plain error rather
than a stack overflow.

## Finding scripts

`pgm do_something` looks for `do_something.py` in this order, first match wins:

1. the current working directory
2. every directory in the `PGM_PATHS` environment variable (`:`-separated,
   searched left to right)
3. the `scripts/` directory shipped inside the `pgm` package

So a file in the directory you are standing in transparently shadows a packaged
one. `pgm --where <name>` prints the file a name resolves to, and `pgm --paths`
prints the search order.

### Folders

A search directory may have folders inside it, and pgm looks through them, so
scripts can be organised without anything having to be told where they went:

```console
$ pgm randint           # finds gen/randint.py, wherever it was put
$ pgm gen/randint       # says which one, when a bare name is not enough
```

Moving a script into a folder therefore does not break the pipelines that use
it. Two folders under one search directory can use the same name, and pgm says
so rather than picking:

```console
$ pgm thing
pgm: 'thing' is ambiguous in /home/you/scripts; it could be generators/thing or
     parsers/thing. Say which one.
```

**The working directory is read only at the top.** It is wherever you happen to
be standing, not a place set aside for scripts, and searching it would turn
every run into a walk of somebody's whole project. A folder there can still be
named outright — `pgm tools/report` — or the directory can be added to
`PGM_PATHS`, which is searched all the way down. Folders whose names start with
a dot or an underscore are never entered, and pgm stops three folders deep.

`pgm --list` shows everything reachable — what each script is, where it came
from, and what it says it does — with shadowed entries marked `#`:

```console
$ pgm --list
  chart            run_all  local    Draw a histogram of everything that came in.
  randint          run      local    Mine, not the packaged one.
# gen/randint      run      package  Emit random integers, one record each.
  stat/count       run_all  package  Count the total number of records that are passed.
  util/hello       run      package  Example pgm script: the record says who, the options say how.
  util/rename_key  run      package  Rename one key in every record: --from=old --to=new.
```

A script is listed under the folder it lives in, so the listing shows how things
are arranged as well as what is there.

**The description is the first line of the script's module docstring.** There is
nothing else to declare and no registry to update: a script says what it does by
saying what it does, in the place you would have written it anyway.

```python
"""Draw a histogram of everything that came in."""
```

The second column is the entry point the file defines, so a listing tells you
which scripts want records one at a time and which want them all at once.
Neither column costs anything to produce: pgm reads these out of the file
without importing it, so listing scripts never runs them, and one that will not
even parse is listed as `?` rather than quietly left out.

## Arguments

`--list`, `--where`, `--paths`, `--traceback`, `--version` and `--help` are
pgm's, that list is closed, and those names are reserved — giving one a value
(`--traceback=true`) is an error rather than an option that quietly turns into
the script's. **Every other option on the line is parsed and handed to the
script as `args`**, whether it comes before the script name or after it:

```console
$ pgm --dry hello                  # {"dry": true}
$ pgm --verbosity=3 hello          # {"verbosity": 3}
$ pgm --logpath=path/to/file hello # {"logpath": "path/to/file"}
$ pgm hello --dry --verbosity=3    # {"dry": true, "verbosity": 3}
```

**A value is always attached with `=`.** There is no `--name value` form, and
that one restriction is what keeps the rest simple:

| on the command line | in `args` |
| --- | --- |
| `--name=value` | `value` |
| `--name` | `true` |
| `--log-path=x` | key `log_path` — dashes become underscores |
| `--offset=-3` | `-3` |

Because every option carries its own value, no token's meaning depends on what
sits next to it. Options can go before the script name, after it, or on both
sides, and the one bare word on the line is always the script to run. Writing a
value with a space is a clear error rather than a misparse:

```console
$ pgm --logpath out.txt hello
pgm: more than one script name on the line ('out.txt', 'hello'); a value
     needs an '=' -- did you mean --logpath=out.txt?
```

A value that is **valid JSON arrives as JSON**, and anything else arrives as a
string — so `--verbosity=3` is the number `3`, `--dry=false` is `false`, and
`--logpath=out.txt` is a string, with no per-script wiring. That is also how you
pass a list: `--tags='["a", "b"]'`. Repeating an option is an error rather than a
silent last-one-wins, and so is a second bare word.

Each record gets its own copy of `args`, so a script that writes into the dict
cannot affect the next call.

## Input

pgm reads stdin and turns it into records, then calls `run` **once per record**
(or `run_all` once, with all of them).

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

The bundled `randint` script returns a list, so it is a ready-made source. Given
a `double.py` next to you:

```python
def run(args: dict, data: dict) -> dict:
    return {"value": data["value"] * 2}
```

three records out of `randint` are three calls into `double`:

```console
$ pgm --count=3 --end=9 randint | pgm double
{"value": 0}
{"value": 16}
{"value": 14}
```

## Errors

Failures print one line on stderr and exit non-zero — a missing script, a file
with no `run`, a `run` that cannot take `(args, data)`, a command line pgm cannot
read, a raised exception, input pgm will not read, or a return value pgm will not
print. Pass `--traceback` to see the full stack when a script raises.

## Development

```console
$ poetry run pytest
```
