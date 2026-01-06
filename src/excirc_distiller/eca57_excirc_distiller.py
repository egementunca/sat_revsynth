"""ECA57 Ex-Circuit Distillation.

Distills identity circuits into "excircuits" (witnesses) - half-circuits that
can be used to detect or verify identity templates.

The pipeline:
1. REC (Raw ExCircuit Collection): Extract min_slice from each identity circuit
2. FEL (Fill Empty Line extensions): Add spectator wires to reach max_width
3. RMR (Remove Reducibles): Remove circuits containing smaller templates
4. RMD (Remove Duplicates): Deduplicate circuits
"""
from __future__ import annotations

from typing import Optional, Callable
from circuit.eca57_collection import ECA57Collection
from circuit.eca57_dim_group import ECA57DimGroup
from gates.eca57 import ECA57Circuit


class ECA57ExCircDistiller:
    """Distills identity circuits into witness templates.
    
    Takes a Collection of identity circuits and produces a Collection of
    "excircuits" - half-circuits that can be used to detect identities.
    
    Example:
        >>> coll = load_identity_collection()  # Full identity circuits
        >>> distiller = ECA57ExCircDistiller(coll)
        >>> witnesses = distiller.distill()
        >>> witnesses.save_json("witnesses.json")
    """
    
    def __init__(self, collection: ECA57Collection):
        """Initialize distiller with identity collection.
        
        Args:
            collection: Collection of identity circuits.
        """
        self._collection = collection
        self._max_width = collection.max_width
        self._max_gate_count = collection.max_gate_count
        # Excircuit gate count is half of identity gate count + 1
        self._max_exc_gc = self._max_gate_count // 2 + 1
    
    def distill(
        self,
        progress_callback: Optional[Callable[[str, int], None]] = None
    ) -> ECA57Collection:
        """Run the distillation pipeline.
        
        Pipeline stages:
        1. REC: Raw ExCircuit Collection (extract min_slice)
        2. FEL: Fill Empty Line extensions
        3. RMR: Remove Reducibles
        4. RMD: Remove Duplicates
        
        Args:
            progress_callback: Optional callback(stage_name, step_number).
            
        Returns:
            Collection of witness circuits (excircuits).
        """
        if progress_callback:
            progress_callback("REC", 0)
        print("0. REC started")
        excircuits = self._raw_excirc_collection()
        
        if progress_callback:
            progress_callback("FEL", 1)
        print("\n1. REC finished - FEL started")
        excircuits.fill_empty_line_extensions()
        
        if progress_callback:
            progress_callback("RMR", 2)
        print("\n2. FEL finished - RMR started")
        excircuits.remove_reducibles()
        
        if progress_callback:
            progress_callback("RMD", 3)
        print("\n3. RMR finished - RMD started")
        excircuits.remove_duplicates()
        
        if progress_callback:
            progress_callback("DONE", 4)
        print("\n4. RMD finished")
        
        return excircuits
    
    def _raw_excirc_collection(self) -> ECA57Collection:
        """Extract raw excircuits by taking min_slice of each identity.
        
        For each identity circuit of length 2n or 2n+1, extracts the first
        n+1 gates as a "witness" template.
        
        Returns:
            Collection of excircuits indexed by (width, exc_gc).
        """
        excircuits = ECA57Collection(self._max_width, self._max_exc_gc)
        
        for width in range(3, self._max_width + 1):
            for exc_gc in range(2, self._max_exc_gc + 1):
                print(f"  -- REC({width}, {exc_gc})")
                
                # Excircuit of length k comes from identities of length 2*(k-1) or 2*(k-1)+1
                gc_a = (exc_gc - 1) * 2  # Even length identity
                gc_b = gc_a + 1  # Odd length identity
                
                ext_list = []
                
                # From even-length identities
                if gc_a >= 2 and gc_a <= self._max_gate_count:
                    if width in self._collection._data and gc_a in self._collection._data.get(width, {}):
                        dg_a = self._collection._data[width].get(gc_a)
                        if dg_a:
                            for circ in dg_a:
                                ext_list.append(circ.min_slice())
                
                # From odd-length identities
                if gc_b >= 2 and gc_b <= self._max_gate_count:
                    if width in self._collection._data and gc_b in self._collection._data.get(width, {}):
                        dg_b = self._collection._data[width].get(gc_b)
                        if dg_b:
                            for circ in dg_b:
                                ext_list.append(circ.min_slice())
                
                if ext_list:
                    if excircuits._data[width][exc_gc] is None:
                        excircuits._data[width][exc_gc] = ECA57DimGroup(width, exc_gc)
                    excircuits._data[width][exc_gc].extend(ext_list)
        
        return excircuits


def distill_cli(collection_path: str, output_path: str) -> None:
    """CLI helper to run distillation on a saved collection.
    
    Args:
        collection_path: Path to identity collection JSON.
        output_path: Path to save witness collection.
    """
    from pathlib import Path
    
    print(f"Loading collection from {collection_path}...")
    coll = ECA57Collection.load_json(Path(collection_path))
    print(f"Loaded: {coll.total_circuits()} identity circuits")
    print()
    
    distiller = ECA57ExCircDistiller(coll)
    witnesses = distiller.distill()
    
    print()
    print(witnesses.summary())
    
    out = Path(output_path)
    witnesses.save_json(out)
    witnesses.save_compact(out.with_suffix(".txt"))
    
    print(f"\nSaved to {out} and {out.with_suffix('.txt')}")
