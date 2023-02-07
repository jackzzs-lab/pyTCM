from itertools import product

from schrodinger.structure import StructureReader, StructureWriter

from .utils import flatten, rename_dup, guess_out_path
from .structure import Structure

def reader(f_path: str, index: int = 1, cls=Structure, **kw):
    with StructureReader(str(f_path), index=index) as reader:
        for st in reader:
            yield cls(st, **kw)


def read_one(f_path: str, index: int = 1, **kw):
    try:
        return next(reader(str(f_path), index=index, **kw))
    except StopIteration:
        return None


def writer(f_path: str, **kw):
    return StructureWriter(str(f_path), **kw)


def write_one(st: Structure, f_path: str, **kw):
    with writer(str(f_path), **kw) as f:
        f.append(st)

def workflow(*inputss, **kw):
    """Iterate over (st_first, *st_others)."""
    for inputs in product(*[flatten(a) for a in inputss]):
         others = [read_one(i, **kw) for i in inputs[1:]]
         for st in reader(inputs[0], **kw):
            if others: 
                yield st, *others
            else:
                yield st

def workflow_output_st(*inputss, out_path=None, use_title=True, ext=None, **kw):
    """Iterate over (output_writer, st_first, *st_others), writer will be generated for each st."""
    for inputs in product(*[flatten(a) for a in inputss]):
        others = [read_one(i, **kw) for i in inputs[1:]]
        if use_title:
            titles = rename_dup([st.title for st in reader(inputs[0], **kw)])
        for i, st in enumerate(reader(inputs[0], **kw)):
            if use_title:
                out_path_guess = guess_out_path(inputs[0], out_path=out_path, name=titles[i], ext=ext)
            else:
                out_path_guess = guess_out_path(inputs[0], out_path=out_path, suffix=i, suffix_mode="force", ext=ext)
            with writer(out_path_guess) as w:
                if others: 
                    yield w, st, *others
                else:
                    yield w, st
                
def workflow_output_file(*inputss, out_path=None, ext=None, **kw):
    """Iterate over (output_writer, st_first, *st_others), writer will be generated for each file."""
    for inputs in product(*[flatten(a) for a in inputss]):
        others = [read_one(i, **kw) for i in inputs[1:]]
        with writer(guess_out_path(inputs[0], out_path=out_path, ext=ext)) as w:
            for st in reader(inputs[0], **kw):
                if others: 
                    yield w, st, *others
                else:
                    yield w, st