from collections import namedtuple

from pdb2sql import StructureSimilarity

SimilarityResult = namedtuple("SimilarityResult", ["irmsd", "lrmsd", "fnat", "dockq"])
            
def get_similarity(inp, ref):
    sim = StructureSimilarity(inp, ref)
    irmsd = sim.compute_irmsd_fast()
    lrmsd = sim.compute_lrmsd_fast()
    fnat = sim.compute_fnat_fast()
    dockq = sim.compute_DockQScore(fnat, lrmsd, irmsd)
    return SimilarityResult(irmsd=irmsd, lrmsd=lrmsd, fnat=fnat, dockq=dockq)