from typing import Iterable

from schrodinger.structutils import measure
from schrodinger.structutils import structalign
from schrodinger.utils import log

from .app import logger
from .files import reader
from .structure import Structure

DEBUG = (log.get_environ_log_level() <= log.DEBUG)    

class _StructAlign(structalign.StructAlign):
    def align(self, ref_st, sts, ref_asl, asl):
        cmdopts = {
            'MODE': 'align',
            'ORDER': 'seed',
            'GAP_OPEN': self._gap_penalty,
            'GAP_DEL': self._deletion_penalty,
            'SSE_MINSIM': self._minimum_similarity,
            'SSE_MINLEN': self._minimum_length
        }
        if self._use_scanning_alignment:
            cmdopts['SSE_WINLEN'] = self._window_length
        if self.use_automatic_settings:
            cmdopts['USE_AUTOMATIC_SETTINGS'] = 'yes'
        std_res = self.use_standard_residues
        reorder = self.reorder_by_connectivity
        output = self.pairwise_align_ct(query=('ref', ref_st),
                                        templist=[('sup', st) for st in sts],
                                        keywords=cmdopts,
                                        log=logger,
                                        debug=DEBUG,
                                        save_props=True,
                                        std_res=std_res,
                                        reorder=reorder,
                                        asl = ref_asl,
                                        asl_mobile = asl)
        return [(out.align, out.stdout) for out in output]

def seq_align(ref_st: Structure, mob_sts: Iterable[Structure], ref_asl: str = None, mob_asl: str = None):
    """Align multiple structures based on sequence alignment."""
    return _StructAlign().align(ref_st=ref_st, sts=mob_sts, ref_asl=ref_asl, asl=mob_asl)

def anchor_distances(st, anchor1, anchor2):
    """Returns the distances between two atoms in protein-protein docking poses."""
    results = []
    for st in reader(input):
        try:
            anchor1a = st.atom[st.eval_asl(anchor1)[0]]
            anchor2a = st.atom[st.eval_asl(anchor2)[0]]
        except TypeError or IndexError:
            logger.error("ASL provided must match a single atom.")
            continue
        results.append(measure.measure_distance(anchor1a, anchor2a))
    return [round(r, 3) for r in results]