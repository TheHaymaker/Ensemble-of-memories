"""Tiny helper for hidden checks: each check is a name and a function; prints a JSON dict.
Names start with 'task:' (did it do what was asked) or 'mem:' (is it consistent with what the
history decided or was told). A check that raises or returns a falsy value (including None from re.match) counts as False."""
import json, os, re, sys, traceback
sys.path.insert(0, os.getcwd())
RESULTS = {}

def check(name):
    def deco(fn):
        try:
            v = fn()
            RESULTS[name] = bool(v)
        except Exception as e:
            RESULTS[name] = False
            RESULTS.setdefault("_errors", {})[name] = f"{type(e).__name__}: {e}"[:200]
        return fn
    return deco

def raises(fn, *args):
    try:
        fn(*args)
    except Exception as e:
        return e
    return None

def readme():
    return open("README.md").read() if os.path.exists("README.md") else ""

def done():
    print(json.dumps(RESULTS))
