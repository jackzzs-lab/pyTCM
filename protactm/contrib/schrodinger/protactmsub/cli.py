# This file is designed to be run with $SCHRODINGER/run.

from __future__ import division, print_function, with_statement

import sys

if sys.version_info[0] < 3:
    raise RuntimeError("this script should only be run with schrodinger python version > 3.")

import json
import random
import logging

logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.NOTSET)

try:
    import click
    import schrodinger
    logging.getLogger("schrodinger.structutils.analyze").propagate = False
except ImportError:
    raise RuntimeError("this script should only be called by ProtacTM.")

from . import utils
from .app import logger
from .files import workflow, workflow_output_st, workflow_output_file
from .protac import TernaryComplex
from .structure import Atoms, SubstructureNotFoundError

logger.debug("Schrodinger subpackage of ProtacTM has been initialized.")


@click.group()
def cli():
    """Cli of schrodinger sub-package, and this script should only be called by ProtacTM."""
    pass

@cli.group(hidden=True)
def debug():
    pass

@cli.group(chain=True)
@utils.inputs()
def ternary_info(input):
    """Print informations about a ternary complex, and required fields are defined by multiple subcommands."""
    pass


@ternary_info.resultcallback()
def output(processors, input):
    results = []
    st: TernaryComplex
    for st in workflow(utils.parse_input(input), cls=TernaryComplex):
        info = {"title": st.title}
        for processor in processors:
            try:
                result = processor(st)
            except SubstructureNotFoundError as e:
                logger.error(f"{str(e)} Skipping.")
                break
            if isinstance(result, dict):
                info.update(result)
            else:
                info[processor.__name__] = result
        else:
            results.append(info)
    click.echo(json.dumps(results))


@ternary_info.command(name="protac")
def protac_smiles():
    """Returns SMARTS of the PROTAC in structure."""

    def protac_smiles(st: TernaryComplex):
        return st.protac.smiles

    return protac_smiles


@ternary_info.command(name="linker")
def linker_smarts():
    """Returns SMARTS of the linker of PROTAC in structure."""

    def linker_smarts(st: TernaryComplex):
        return st.protac.linker.smarts

    return linker_smarts


@ternary_info.command(name="ligands")
def ligands_smarts():
    """Returns SMARTS of two ligand parts of PROTAC in structure."""

    def ligands_smarts(st: TernaryComplex):
        return [l.smarts for l in st.protac.ligands]

    return ligands_smarts


@ternary_info.command(name="partners")
def partner_chains():
    """Returns the chain of PROTAC neighboring proteins (E3 ligase and target proteins)."""

    def partner_chains(st: TernaryComplex):
        return [list(dict.fromkeys(c.name for c in cl)) for cl in st.partners.values()]

    return partner_chains


@cli.group()
def ternary():
    """Operations to modify ternary complexes."""
    pass


@ternary.command()
@utils.inputs()
@utils.outputs()
@click.option("--poses", "-n", default=1, help="Poses to be generated.")
@click.option("--chains", "-c", type=str, help="Chains to be transformed.")
@click.option("--keep-anchors", "-k", is_flag=True, help="Keep the anchor atom between linker and the ligands.")
@click.option("--seed", type=str, help="Seed for random generator.")
@click.option("--trans", nargs=2, type=float, default=(-50, 50), help="Range of translation in Å.")
@click.option("--rot", nargs=2, type=float, default=(-180, 180), help="Range of rotation in degree.")
@click.option("--torrence", default=0, help="Allowed clashes for generated poses.")
def input_gen(input, output, poses, chains, keep_anchors, seed, trans, rot, torrence):
    """Generate input poses by randomly transform a partner."""
    st: TernaryComplex
    for w, st in workflow_output_st(utils.parse_input(input), out_path=output, cls=TernaryComplex):
        st.protac.pdbres
        try:
            pose = 0
            if not chains:
                chain_lens = {k: sum(len(c) for c in cl) for k, cl in st.partners.items()}
                chains_list = list(set(c.name for c in st.partners[min(chain_lens, key=chain_lens.get)]))
            else:
                chains_list = chains.split(",")
            while pose < poses:
                stp = st.copy(editable=True)
                # migrate pre-detected ligands to processing pose
                partners_ligands = {}
                for l in st.protac.ligands:
                    if keep_anchors:
                        la = l.with_anchors().with_hydrogens().copy(st=stp, real=True)
                    else:
                        la = l.with_hydrogens().copy(st=stp, real=True)
                    partners_ligands[l.partner.name] = la
                keep_atoms = utils.flatten2(partners_ligands.values())
                delete_atoms = [a for a in st.protac.linker.with_hydrogens() if a not in keep_atoms]
                stp.deleteAtoms(delete_atoms)
                la: Atoms
                for p, la in partners_ligands.items():
                    for a in la.atoms():
                        a.chain = p
                al = stp.chains_atoms(chains_list)
                other_al = [a.index for a in stp.atom if a.index not in al]
                random.seed(seed)
                stp.rotate_atoms(al, random.uniform(*rot), random.uniform(*rot), random.uniform(*rot))
                stp.translate_atoms(al, random.uniform(*trans), random.uniform(*trans), random.uniform(*trans))
                if utils.count(stp.clashes_between(al, other_al)) <= torrence:
                    pose += 1
                    w.append(stp)
                    logger.info(f'Accepted pose for "{st.title}" ({pose}/{poses}).')
                else:
                    logger.info(f"Rejected pose due to unacceptable clash (>{torrence}).")
        except SubstructureNotFoundError as e:
            logger.error(f"{str(e)} Skipping.")
            continue

@cli.group()
def pppose_info():
    """Analyze informations about protein-protein docking poses."""
    pass


@pppose_info.command()
@utils.inputs()
@click.option("--anchor1", "-1", required=True, type=str, help="ASL for anchor atom 1.")
@click.option("--anchor2", "-2", required=True, type=str, help="ASL for anchor atom 2.")
def anchor_distances(input, anchor1, anchor2):
    """Returns the distances between two atoms in protein-protein docking poses."""
    from schrodinger.structutils import measure
    results = []
    for st in workflow(input):
        try:
            anchor1a = st.atom[st.eval_asl(anchor1)[0]]
            anchor2a = st.atom[st.eval_asl(anchor2)[0]]
        except TypeError or IndexError:
            logger.error("ASL provided must match a single atom.")
            continue
        results.append(measure.measure_distance(anchor1a, anchor2a))
    return [round(r, 3) for r in results]

if __name__ == "__main__":
    cli()
