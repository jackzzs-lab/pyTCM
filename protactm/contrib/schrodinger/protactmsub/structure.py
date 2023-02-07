from __future__ import annotations
from functools import cached_property

import math
from collections import Counter
from typing import Generator, Iterable, Union, List

from schrodinger.structutils import analyze, assignbondorders, transform as tf
from schrodinger.structutils.analyze import Ligand
from schrodinger.structutils.interactions.steric_clash import clash_iterator
from schrodinger.structure import _StructureAtom as Atom, _Chain as Chain, Structure as _Structure

from . import utils
from .app import logger

class SubstructureNotFoundError(Exception):
    pass

class Atoms(list):
    @classmethod
    def from_atom(cls, atom: Atom, **kw):
        """Return an Atoms instance of a single atom. Structure is set automatically. Reality is set based on structure settings."""
        return cls([atom], **kw)

    @classmethod
    def from_chains(cls, chains: Iterable[Union[Chain, ChainAtoms]], **kw):
        """Return an Atoms instance of a list of Chain. Structure is set automatically. Reality is False."""
        atoms = []
        for c in chains:
            if isinstance(c, ChainAtoms):
                atoms.extend(c)
                st = c.st
            elif isinstance(c, Chain):
                atoms.extend(c.getAtomIndices())
                st = Structure(c.structure)
            else:
                raise ValueError(f"{type(c)} is not accepted for creating an Atoms object.")
        return cls(atoms, st=st, real=False, **kw)

    def __init__(self, atoms: Iterable[Union[int, Atom]], st: Structure = None, real: bool = None):
        if isinstance(atoms, Atoms) and not st:
            st = atoms.st
        atoms = list(atoms)
        if not atoms:
            raise ValueError(f"can not create Atoms with an empty list.")
        elif isinstance(atoms[0], int):
            if not st:
                raise ValueError("if the input is a list of atom indices, st must be provided explicitly.")
            if real is None:
                real = st.is_editable()
            if real:
                atoms = [st.atom[a_id] for a_id in atoms]
        elif isinstance(atoms[0], Atom):
            if not st:
                st = Structure(atoms[0].structure)
            if real is None:
                real = st.is_editable()
            if real:
                atoms = [a.index for a in atoms]
        else:
            raise ValueError(f"{type(atoms[0])} is not accepted for creating an Atoms object.")
        super().__init__(atoms)
        self._st = st
    
    def __getitem__(self, index):
        if self.is_real():
            return list.__getitem__(self, index).index
        else:
            return list.__getitem__(self, index)

    def __iter__(self):
        for i in super().__iter__():
            if self.is_real():
                yield i.index
            else:
                yield i

    def __repr__(self):
        result = f"{self.__class__.__name__}({len(self)}) at {self.st}"
        if self.is_real():
            result += ", real"
        return f"<{str(result)}>"
    
    def __hash__(self):
        return hash((self.st.handle, tuple(self.atoms())))
    
    def __add__(self, other):
        if not isinstance(other, Atoms):
            raise TypeError('add operation is only allowed between Atoms.')
        if self.st != other.st:
            raise TypeError('add operation between different structures makes no sense.')
        if self.is_real() or other.is_real():
            return Atoms({*self.atoms(), *other.atoms()})
        else:
            return Atoms({*self, *other})

    @property
    def st(self) -> Structure:
        return self._st

    @property
    def asl(self) -> str:
        return analyze.generate_asl(self.st, self)

    @property
    def smarts(self) -> str:
        return analyze.generate_smarts_canvas(self.extract())

    def is_real(self):
        """Return the reality, that means, Atom is stored by instance rather than index, and can stand any atom deletion."""
        if len(self) == 0:
            return False
        else:
            return isinstance(list.__getitem__(self, 0), Atom)

    def copy(self, **kw):
        new = self.__class__(self)
        return new.convert(**kw)

    def convert(self, st: Structure = None, real: bool = None):
        if real is None:
            real = self.is_real()
        if st is None:
            st = self.st
        if st != self.st:
            if st.atom_total != self.st.atom_total:
                raise ValueError("target structure does not match the number of atoms in the original structure.")
            if self.is_real():
                for i in range(len(self)):
                    list.__setitem__(self, i, list.__getitem__(self, i).index)
            self._st = st
        if real != self.is_real():
            if real:
                for i in range(len(self)):
                    list.__setitem__(self, i, self.st.atom[list.__getitem__(self, i)])
            else:
                for i in range(len(self)):
                    list.__setitem__(self, i, list.__getitem__(self, i).index)
        return self

    def atoms(self) -> Generator[Atom, None, None]:
        for a_id in self:
            yield self.st.atom[a_id]

    def contact_chains(self, within: float = 4, sort=False) -> List[ChainAtoms]:
        """Return the chains within certain distances, when sort=True, results will be ordered by number of nearby atoms."""
        al = self.st.eval_asl(f"(within {within} ({self.asl})) AND NOT ({self.asl})")
        if sort:
            return [ChainAtoms.from_chain(i) for i, _ in Counter(a.getChain() for a in al.atoms()).most_common()]
        else:
            return [ChainAtoms.from_chain(i) for i in {a.getChain() for a in al.atoms()}]

    def extract(self, copy_props: bool = False):
        return Structure(self.st.extract(self, copy_props))

    def bonded_atoms(self):
        """Iterate over atoms bonded to any atoms in self."""
        for a in self.atoms():
            for ba in a.bonded_atoms:
                if ba.element != "H" and ba.index not in self:
                    yield ba

    def expandable_atoms(self, nbonds: int = 1):
        """Iterate over all atoms in self, that can be expand by n bonds to nearby atoms."""
        for a in self.atoms():
            if utils.min_len(self.st.expand_shells([self, Atoms.from_atom(a)]), nbonds):
                yield a
    
    def bonded_hydrogens(self):
        for a in self.atoms():
            for ba in a.bonded_atoms:
                if ba.element == "H" and ba.index not in self:
                    yield ba

    def with_hydrogens(self):
        return self + Atoms(self.bonded_hydrogens())

class LigandAtoms(Atoms):
    @classmethod
    def from_ligand(cls, ligand: Ligand, st: Structure, **kw):
        """Return an Atoms instance of a Ligand. Structure should be provided explicitly. Reality is set based on structure settings."""
        return cls(ligand.atom_indexes, st=st, mol_num=ligand.mol_num, asl=ligand.ligand_asl, **kw)
    
    def __init__(self, *args, mol_num: int = None, asl: str = None, **kw):
        super().__init__(*args, **kw)
        self._mol_num = mol_num
        self._asl = asl

    def __repr__(self):
        result = f"{self.__class__.__name__}({self.pdbres.strip()}) at {self.st}"
        if self.is_real():
            result += ", real"
        return f"<{str(result)}>"

    @property
    def mol_num(self):
        return self._mol_num

    @property
    def asl(self):
        return self._asl

    @cached_property
    def chain(self):
        return ChainAtoms.from_chain(next(self.atoms()).getChain())

    @cached_property
    def pdbres(self):
        results = []
        for a in self.atoms():
            if a.pdbres not in results:
                results.append(a.pdbres)
        return results[0] if len(results) == 1 else results
    
    @cached_property
    def resnum(self):
        results = []
        for a in self.atoms():
            if a.resnum not in results:
                results.append(a.resnum)
        return results[0] if len(results) == 1 else results

    @cached_property
    def nxgraph(self):
        return analyze.create_nx_graph(self.st, self)

    @cached_property
    def st_lig(self):
        return self.extract()

    @cached_property
    def smiles(self) -> str:
        return analyze.generate_smiles(self.st_lig, unique=True, stereo="annotation_and_geom")

    def eval_smarts(self, smarts):
        return self.st.eval_smarts(smarts, mols_only=[self.mol_num])

    def __str__(self):
        return self.smiles


class ChainAtoms(Atoms):
    @classmethod
    def from_chain(cls, chain: Chain, **kw):
        if not issubclass(cls, ChainAtoms):
            cls = ChainAtoms
        """Return an Atoms instance of a Chain. Structure is set automatically. Reality is False."""
        return cls(chain.getAtomIndices(), st=Structure(chain.structure), chain=chain.name, real=False, **kw)
    
    def __init__(self, *args, chain: str = None, **kw):
        super().__init__(*args, **kw)
        self._chain = chain

    def __repr__(self):
        result = f"{self.__class__.__name__}({self.name}) at {self.st}"
        if self.is_real():
            result += ", real"
        return f"<{str(result)}>"

    @property
    def name(self):
        return self._chain

    @name.setter
    def name(self, value):
        for a in self.atoms():
            a.chain = value
        self._chain = value


class Structure(_Structure, utils.Patcher):
    def __upgrade__(self):
        self._editable = False

    def is_editable(self):
        return self._editable

    def copy(self, editable: bool = None):
        if editable is None:
            editable = self._editable
        new = self.__class__(self.__copy__())
        new._editable = editable
        return new

    def atoms(self, l, cls=Atoms, **kw):
        return cls(l, st=self, **kw)

    def chains_atoms(self, l, cls=ChainAtoms, **kw) -> List:
        return [cls.from_chain(c, **kw) for c in self.chain if c.name in l]
    
    def chain_atoms(self, c, **kw):
        return self.chains_atoms([c], **kw)[0]
        
    def rotate_atoms(self, atoms: Atoms, x_angle: float, y_angle: float, z_angle: float):
        centroid = tf.get_centroid(self, atoms)
        displacement_vector = tf.get_coords_array_from_list(centroid)
        to_origin_matrix = tf.get_translation_matrix(-1 * displacement_vector)
        tf.transform_structure(self, to_origin_matrix)
        rot_matrix_x = tf.get_rotation_matrix(tf.X_AXIS, math.radians(x_angle))
        rot_matrix_y = tf.get_rotation_matrix(tf.Y_AXIS, math.radians(y_angle))
        rot_matrix_z = tf.get_rotation_matrix(tf.Z_AXIS, math.radians(z_angle))
        tf.transform_structure(self, rot_matrix_x, atoms)
        tf.transform_structure(self, rot_matrix_y, atoms)
        tf.transform_structure(self, rot_matrix_z, atoms)
        from_origin_matrix = tf.get_translation_matrix(displacement_vector)
        tf.transform_structure(self, from_origin_matrix)

    def translate_atoms(self, atoms: Atoms, x: float, y: float, z: float):
        trans_matrix = tf.get_translation_matrix([x, y, z])
        tf.transform_structure(self, trans_matrix, atoms)

    def eval_asl(self, asl: str):
        if not analyze.validate_asl(asl):
            logger.error(f'ASL "{asl}" is not valid.')
            return
        return self.atoms(analyze.evaluate_asl(self, asl))

    def eval_smarts(self, smarts: str, mols_only: Iterable[int] = None, **kw):
        vali, _ = analyze.validate_smarts_canvas(smarts)
        if not vali:
            logger.error(f'SMARTS "{smarts}" is not valid.')
            return
        if mols_only:
            matches = analyze.evaluate_smarts_by_molecule(self, smarts, molecule_numbers=mols_only, **kw)
        else:
            matches = analyze.evaluate_smarts_canvas(self, smarts, **kw)
        return [self.atoms(al) for al in matches]

    def clashes_between(self, atoms1: Atoms, atoms2: Atoms, **kw):
        return clash_iterator(self, atoms1=atoms1, atoms2=atoms2, **kw)

    def expand_shells(self, shells: List[Atoms]):
        """
        From [a1, a2, a3, ..., a(n)], yield a(n+1) as one bond expanded from a(n), excluding atoms
        from [a1, a2, a3, ..., a(n-1)].

        Args:
            shells (List[Atoms]): a list of shells defining the expand space

        Yields:
            Atoms: a shell as one bond expanded from the outer shell in shells
        """
        while True:
            shell = []
            for a in shells[-1].atoms():
                for ba in a.bonded_atoms:
                    if ba.element != "H" and ba.index not in utils.flatten2(shells):
                        shell.append(ba.index)
            if shell:
                shells.append(self.atoms(shell))
                yield shells[-1]
            else:
                break

    def expand_shells_to_molecular(self, shells: List[Atoms]):
        """

        
        Args:
            shells (List[Atoms]): a list of shells defining the expand space

        Returns:
            _type_: _description_
        """
        return self.atoms(set(utils.flatten2(self.expand_shells(shells))))
    
    def assign_bond_orders(self):
        return assignbondorders.assign_st(self, skip_assigned_residues=True, use_ccd=True)
