import itertools
from functools import wraps
from pathlib import Path
from types import FunctionType
from typing import Iterable, Iterator, Type
from datetime import datetime

import click


def inputs(*args, argument=False, required=True, multiple=True):
    """Decorator for adding a input option/argument, allowing files or dirs.

    Args:
        argument (bool, optional): Add an argument instead of option. Defaults to False.
        required (bool, optional): Defaults to True.
        multiple (bool, optional): If False, allow only one file. Defaults to True.
    """
    if not argument:
        args = args if args else ["--input", "-i"]
        return click.option(
            *args,
            required=required,
            multiple=multiple,
            type=click.Path(dir_okay=multiple, exists=True, readable=True),
            help="Input file/dir containing structures.",
        )
    else:
        nargs = -1 if multiple else 1
        args = args if args else ["input"]
        return click.argument("input", nargs=nargs, type=click.Path(dir_okay=multiple, exists=True, readable=True))


def outputs():
    """Decorator for adding a output option."""
    return click.option("--output", "-o", type=click.Path(writable=True), help="Path of the output dir or file.")


def count(iter: Iterator):
    """Count total item number of an iterator."""
    return sum(1 for _ in iter)


def min_len(iter: Iterator, min_len: int = None):
    """Check if an iterator has items more than min_len."""
    for _ in range(min_len):
        try:
            _ = next(iter)
        except StopIteration:
            return False
    return True


def class_path(c: Type) -> str:
    """Return full path of a class."""
    module = c.__module__
    if module == "builtins":
        return c.__qualname__  # avoid outputs like 'builtins.str'
    return module + "." + c.__qualname__


def flatten(l: Iterable[Iterable]):
    """Flatten a irregular n-dimensional list to a 1-dimensional list."""
    for el in l:
        if isinstance(el, Iterable) and not isinstance(el, (str, bytes)):
            yield from flatten(el)
        else:
            yield el


def flatten2(l: Iterable[Iterable]):
    """Flatten a 2-dimensional list to a 1-dimensional list."""
    return [item for sublist in l for item in sublist]


def rename_dup(l: Iterable[str]):
    """Rename duplicated names in a list with increasing suffixes."""
    results = []
    for i, v in enumerate(l):
        totalcount = l.count(v)
        count = l[:i].count(v)
        results.append(v + "_" + str(count + 1) if totalcount > 1 else v)
    return results


def truncate_path(f, length):
    """Truncate a path str to a certain length, and the omitted part is represented by "..."."""
    if Path.cwd() in Path(f).parents:
        return "./" + str(Path(f).relative_to(Path.cwd()))
    else:
        result = Path(*Path(f).parts[-length:])
        if result.is_absolute():
            return str(result)
        else:
            return ".../" + str(result)


def remove_prefix(text, prefix):
    """Remove prefix from the begining of test."""
    return text[text.startswith(prefix) and len(prefix) :]


def get_after_char(text, delim):
    """Get characters after the first occurence of delim."""
    return text[text.index(delim) + len(delim) :]


def truncate_str(text, length):
    """Truncate a str to a certain length, and the omitted part is represented by "..."."""
    return (text[: length + 3] + "...") if len(text) > length else text


def product_nested(l):
    """Product an irregular 2-dimensional list."""
    return itertools.product(*[i if isinstance(i, list) else [i] for i in l])


def parse_input(input, ext=None):
    """Parse a list of input path of dir or file to lists of files.

    Args:
        input (list or str): path or list of paths of input dirs or files.
        ext (str, optional): extension to be searched in dirs, such as ".pdb". Defaults to None, meaning all dirs will be ignored.

    Returns:
        1. list of files: when input is a str, or input is a list and only contains files.
        2. list of list of files: when input is a list containing at least one dirs.
    """
    results = []
    if isinstance(input, Iterable):
        for f in input:
            f = Path(f)
            if f.is_file():
                results.append([f])
            elif f.is_dir() and ext:
                results.append(list(f.glob(f"*{ext}")))
            else:
                raise IOError(f'Input files in: {", ".join(input)} are not found.')
        if all(len(i) == 1 for i in results):
            return list(flatten(results))
    else:
        f = Path(input)
        if f.is_file():
            return [f]
        elif f.is_dir() and ext:
            return list(f.glob(f"*{ext}"))
        else:
            raise IOError(f"Input files in: {input} are not found.")


def guess_out_path(in_path: str, out_path: str = None, name=None, ext=None, suffix=None, suffix_mode="disabled"):
    """Guess output filename based on input file.

    Args:
        in_path: the path of the processing file.
        out_path: the path of the output dir or path. Defaults to the dir path of in_path.
        name: the filename of the output file. Defaults to the filename of in_path.
        ext: the extension of the output file. Defaults to the extension of in_path.
        suffix: the suffix to be attached to the file name. Defaults to current "mmddhh".
        suffix_mode:
            If "disabled" (default), the suffix will be not be added.
            If "force", the suffix will be attached anyway.
            If "auto", the suffix will only be attached when there is a file name conflict.
    """
    in_path = Path(in_path)
    if not in_path.is_file():
        raise ValueError("in_path must be path to an existing file.")
    if out_path:
        if Path(out_path).is_file():
            return out_path
        elif Path(out_path).is_dir():
            out_dir = Path(out_path)
        else:
            return out_path
    else:
        out_dir = in_path.parent
    if not name:
        name = str(in_path.name).rstrip("".join(in_path.suffixes))
    if not ext:
        ext = "".join(in_path.suffixes)
    if suffix_mode == "force" or (suffix_mode == "auto" and out_path.exists()):
        if not suffix:
            suffix = datetime.now().strftime("%m/%d/%Y")
        out_path = out_dir / "{}-{}{}".format(name, suffix, ext)
    else:
        out_path = out_dir / "{}{}".format(name, ext)
        if in_path == out_path:
            raise ValueError("input path and output path will be the same.")
    return out_path.resolve()


class Singleton(type):
    """A metaclass to create a singleton."""

    _instances = {}

    def __call__(cls, *args, **kw):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kw)
        return cls._instances[cls]


class LazyLoad(type):
    """A metaclass to run __load__ after calling certain functions."""

    @staticmethod
    def initialize_before(func):
        @wraps(func)
        def wrapper(obj, *wargs, **wkw):
            if not object.__getattribute__(obj, "__loaded"):
                object.__setattr__(obj, "__loaded", True)
                obj.__load__()
            return func(obj, *wargs, **wkw)

        return wrapper

    def __call__(cls, *args, **kw):
        obj = super().__call__(*args, **kw)
        object.__setattr__(obj, "__loaded", False)
        return obj

    def __new__(cls, name, supers, attrs, triggers=[]):
        for name, item in attrs.items():
            if name in triggers and type(item) is FunctionType:
                attrs[name] = LazyLoad.initialize_before(attrs[name])
        return super().__new__(cls, name, supers, attrs)


class PatcherMeta(type):
    """A transparent proxy metaclass that run __upgrade__ for patching existing classes without changing its fingerprint."""

    def __call__(cls, *args, **kw):
        chain = [cls]
        while type(chain[-1]) == type(cls):
            chain.append(chain[-1].__base__)
        if len(args) == 1 and not kw and isinstance(args[0], chain[-1]):
            if not isinstance(args[0], cls.__base__):
                obj = cls.__base__(args[0])
            else:
                obj = args[0]
            obj.__class__ = cls
        else:
            obj = super(type(cls), cls).__call__(*args, **kw)
        for p in reversed(chain[:-1]):
            try:
                p.__upgrade__(obj)
            except AttributeError:
                continue
        return obj


class Patcher(metaclass=PatcherMeta):
    pass


class ProxyBase:
    """
    A proxy class that make accesses just like direct access to __subject__ if not overwriten in the class.
    Attributes defined in class.__noproxy__ will not be proxied to __subject__.
    """

    __slots__ = ()
    
    def __call__(self, *args, **kw):
        return self.__subject__(*args, **kw)

    def __getattribute__(self, attr, oga=object.__getattribute__):
        if attr.startswith("__") and attr not in ("__class__", "__dict__"):
            subject = oga(self, "__subject__")
            if attr == "__subject__":
                return subject
            return getattr(subject, attr)
        return oga(self, attr)

    def __getattr__(self, attr, oga=object.__getattribute__):
        return getattr(oga(self, "__subject__"), attr)

    def __setattr__(self, attr, val, osa=object.__setattr__):
        if attr == "__subject__" or (hasattr(self.__class__, '__noproxy__') and attr in self.__class__.__noproxy__):
            return osa(self, attr, val)
        return setattr(self.__subject__, attr, val)

    def __delattr__(self, attr, oda=object.__delattr__):
        if attr == "__subject__" or hasattr(type(self), attr) and not attr.startswith("__"):
            oda(self, attr)
        else:
            delattr(self.__subject__, attr)

    def __bool__(self):
        return bool(self.__subject__)

    def __getitem__(self, arg):
        return self.__subject__[arg]

    def __setitem__(self, arg, val):
        self.__subject__[arg] = val

    def __delitem__(self, arg):
        del self.__subject__[arg]

    def __getslice__(self, i, j):
        return self.__subject__[i:j]

    def __setslice__(self, i, j, val):
        self.__subject__[i:j] = val

    def __delslice__(self, i, j):
        del self.__subject__[i:j]

    def __contains__(self, ob):
        return ob in self.__subject__

    for name in "repr str hash len abs complex int long float iter".split():
        exec("def __%s__(self): return %s(self.__subject__)" % (name, name))

    for name in "cmp", "coerce", "divmod":
        exec("def __%s__(self, ob): return %s(self.__subject__, ob)" % (name, name))

    for name, op in [("lt", "<"), ("gt", ">"), ("le", "<="), ("ge", ">="), ("eq", " == "), ("ne", "!=")]:
        exec("def __%s__(self, ob): return self.__subject__ %s ob" % (name, op))

    for name, op in [("neg", "-"), ("pos", "+"), ("invert", "~")]:
        exec("def __%s__(self): return %s self.__subject__" % (name, op))

    for name, op in [
        ("or", "|"),
        ("and", "&"),
        ("xor", "^"),
        ("lshift", "<<"),
        ("rshift", ">>"),
        ("add", "+"),
        ("sub", "-"),
        ("mul", "*"),
        ("div", "/"),
        ("mod", "%"),
        ("truediv", "/"),
        ("floordiv", "//"),
    ]:
        exec(
            (
                "def __%(name)s__(self, ob):\n"
                "    return self.__subject__ %(op)s ob\n"
                "\n"
                "def __r%(name)s__(self, ob):\n"
                "    return ob %(op)s self.__subject__\n"
                "\n"
                "def __i%(name)s__(self, ob):\n"
                "    self.__subject__ %(op)s=ob\n"
                "    return self\n"
            )
            % locals()
        )

    del name, op

    def __index__(self):
        return self.__subject__.__index__()

    def __rdivmod__(self, ob):
        return divmod(ob, self.__subject__)

    def __pow__(self, *args):
        return pow(self.__subject__, *args)

    def __ipow__(self, ob):
        self.__subject__ **= ob
        return self

    def __rpow__(self, ob):
        return pow(ob, self.__subject__)
