from __future__ import annotations

import itertools
from functools import cached_property
from typing import Iterable, List

from networkx.algorithms import boundary
from schrodinger.structutils import analyze

from . import utils
from .app import logger
from .structure import Atom, Atoms, ChainAtoms, Ligand, LigandAtoms, Structure, SubstructureNotFoundError

logger = logger.getChild(__name__)

class Protac(LigandAtoms):
    @cached_property
    def linker(self):
        return self.guess_linker()

    @cached_property
    def partners(self):
        return self.guess_partners()

    @cached_property
    def ligands(self) -> List[ProtacPart]:
        """ Return a list of ProtacPart by spliting the PROTAC into two ligands."""
        result = []
        for anchor in self.linker.anchors.atoms():
            result.append(
                ProtacPart(
                    self.st.expand_shells_to_molecular([self.linker, Atoms.from_atom(anchor)]),
                    anchors=[anchor],
                    type="ligand"
                )
            )
        return result
    
    def partner_ligand(self, partner):
        for l in self.ligands:
            if l.partner.name == partner:
                return l
        else:
            raise ValueError(f'chain "{partner}" is not found as a partner of any ligand.')

    def guess_linker(self):
        fragments = []
        # extract common skeletons from SMARTS (CC, CCO, peptide bond, CC#CC)
        for smarts in ["[H2&C]", "[H2&C]O", "[R1&N]", "O=CN", "C#C"]:
            matches = self.eval_smarts(smarts)
            if matches:
                fragments.extend([set(al) for al in matches])
        # extract common skeletons from rings (N-rings or benzene with 2 sidechains)
        smartses = []
        smartses.append("@".join(["[c&R1]"] * 6))
        for n in range(3, 6):
            smartses.append("@".join(["[#7&R1]"] + ["[#7,#6&R1]"] * n))
        for smarts in smartses:
            matches = self.eval_smarts(smarts)
            for al in matches:
                if utils.count(al.bonded_atoms()) == 2:
                    fragments.append(set(al))

        # check fragment linkage
        while True:
            for f1, f2 in itertools.combinations(fragments, 2):
                if len(f1 & f2) > 0 or utils.count(boundary.edge_boundary(self.nxgraph, f1, f2)) > 0:
                    fragments = [f for f in fragments if f not in [f1, f2]]
                    fragments.append(f1 | f2)
                    break
            else:
                break

        # get largest fragment
        if fragments:
            atom_numbers = [len(f) for f in fragments]
            largest_fragment = fragments[atom_numbers.index(max(atom_numbers))]
            return ProtacPart(largest_fragment, st=self.st, type="linker")
        else:
            raise SubstructureNotFoundError(f"Can not found any linker in PROTAC {self.smiles}.")

    def guess_partners(self):
        result = {}
        c1s = self.contact_chains()
        for c1 in c1s:
            shells: List[List[ChainAtoms]] = [[self.chain], c1s, [c1]]
            while True:
                shell = []
                for sc in shells[-1]:
                    for cc in sc.contact_chains():
                        if cc.name not in (c.name for cl in shells for c in cl):
                            shell.append(cc)
                if shell:
                    shells.append(shell)
                else:
                    break
            result[c1.name] = utils.flatten2(shells[2:])
        return result

    def standardize(self, chain="X", pdbres="PR1"):
        self.chain.name = chain
        for a in self.atoms():
            a.pdbres = pdbres
        return self


class ProtacPart(Atoms):
    def __init__(self, *args, anchors: Iterable[Atom] = None, type: str = None, **kw):
        super().__init__(*args, **kw)
        self._anchors = anchors
        self._type = type

    @cached_property
    def anchors(self):
        if self._anchors:
            return Atoms(self._anchors)
        else:
            return Atoms(self.expandable_atoms())

    @property
    def type(self):
        return self._type

    @cached_property
    def partner(self):
        contact_chains = self.contact_chains(sort=True)
        if contact_chains:
            return contact_chains[0]
        else:
            return None
    
    def with_anchors(self):
        if self.type == "ligand":
            return self + self.anchors
        elif self.type == "linker":
            return self

class TernaryComplex(Structure, utils.Patcher):
    @cached_property
    def protac(self):
        return self.guess_protac()

    @property
    def partners(self):
        return self.protac.partners

    def _is_valid_protac(self, ligand: Ligand):
        # not covalently bonded
        if ligand.is_covalently_bound:
            return False
        # not peptide
        if "-" in ligand.pdbres:
            return False
        # within 4A of >2 chains
        if len(LigandAtoms.from_ligand(ligand, st=self).contact_chains()) < 2:
            return False
        return True
        

    def guess_protac(self):
        for restrictions in ("tight", "loose"):
            if restrictions == "tight":
                ligands = analyze.find_ligands(self, max_atom_count=150, allow_amino_acid_only_molecules=False)
            else:
                logger.debug(f'No PROTAC can be found in structure {self.title}, retry with loose restrictions.')
                ligands = analyze.find_ligands(self, max_atom_count=300)
            if len(ligands) == 0:
                continue
            if len(ligands) == 1 and self._is_valid_protac(ligands[0]):
                    return Protac.from_ligand(ligands[0], st=self)
            if len(ligands) > 1:
                filtered_ligands = [l for l in ligands if self._is_valid_protac(l)]
                if not filtered_ligands:
                    continue
                atom_numbers = [len(f.atom_indexes) for f in filtered_ligands]
                largest_ligand = filtered_ligands[atom_numbers.index(max(atom_numbers))]
                return Protac.from_ligand(largest_ligand, st=self)
        else:
            raise SubstructureNotFoundError(f"Can not found any PROTAC in structure {self.title}.")
