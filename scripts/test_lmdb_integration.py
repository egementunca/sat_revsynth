import sys
import os
import shutil
import time

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from database.lmdb_env import TemplateDBEnv
from database.basis import ECA57Basis, BASIS_ECA57
from database.templates import TemplateStore, OriginKind, decode_gates_eca57
from database.unroll import unroll_and_insert, UnrollConfig, UNROLL_MIRROR, UNROLL_PERMUTE
from database.witnesses import WitnessStore

def test_integration():
    db_path = "/tmp/test_eca57_lmdb"
    
    # Clean up previous run
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    
    print(f"Creating DB at {db_path}...")
    env = TemplateDBEnv(db_path)
    basis = ECA57Basis()
    store = TemplateStore(env, basis)
    witness_store = WitnessStore(env, basis)
    
    # 1. Insert a test template that effectively demonstrates unrolling
    # Circuit: [(0, 1, 2), (1, 2, 0)]
    # This is asymmetric, so mirror and some permutations should be distinct
    gates = [(0, 1, 2), (1, 2, 0)]
    width = 3
    
    print("Inserting seed template...")
    # NOTE: origin=SAT just for testing, though this simple pair isn't an identity
    record = store.insert_template(gates, width, origin=OriginKind.SAT)
    assert record is not None
    assert record.template_id == 1
    assert record.basis_id == BASIS_ECA57
    assert record.gate_count == 2
    
    print(f"  Inserted template ID {record.template_id}, Hash: {record.canonical_hash.hex()[:8]}...")
    
    # 2. Verify we can retrieve it
    retrieved = store.get_by_hash(width, 2, record.canonical_hash)
    assert retrieved is not None
    assert retrieved.template_id == 1
    
    # 3. Unroll
    print("Unrolling template...")
    # Permuting wires: (0,1,2) -> (1,2,0)
    # This should generate new canonical hashes
    config = UnrollConfig(
        do_mirror=True, 
        do_permute=True, 
        do_rotate=True,
        do_swap_dfs=True,
        swap_dfs_budget=10
    )
    
    inserted, dups = unroll_and_insert(store, record, gates, width, config)
    print(f"  Unroll result: {inserted} new variants, {dups} duplicates")
    
    # We expect at least a few variants from permutations
    assert inserted > 0
    
    # 4. Verify family tracking
    family_members = store.get_family_members(record.family_hash)
    print(f"  Family members: {len(family_members)}")
    assert len(family_members) == inserted + 1  # Original + new variants
    assert record.template_id in family_members
    
    # 5. Extract witnesses
    print("Building witnesses...")
    # For GC=2, witness len = floor(2/2) + 1 = 2 (so full circuit)
    # For valid identities, witnesses might just be the circuit itself in this tiny case
    
    wit_count = 0
    for tmpl in store.iter_by_dims(width, 2):
        wit_record = witness_store.build_witnesses_from_template(tmpl)
        if wit_record:
            wit_count += 1
            
    print(f"  Extracted {wit_count} unique witnesses")
    assert wit_count > 0
    
    # 6. Check prefilter
    # Pick a witness and look it up by token
    wit_record = witness_store.get_by_hash(width, 2, record.canonical_hash)
    # Note: witness hash == template hash here because len=2 matches full circuit
    
    if wit_record:
        # Re-compute token for first k-gram
        from database.witnesses import compute_kgram_tokens
        # Use the gates we inserted
        tokens = compute_kgram_tokens(gates, 2, basis, width)
        if tokens:
            token = tokens[0]
            hits = witness_store.lookup_by_token(width, token)
            print(f"  Prefilter lookup for token {token}: {len(hits)} hits")
            assert wit_record.witness_id in hits
    
    print("\nSUCCESS: All integration checks passed!")
    env.close()

if __name__ == "__main__":
    test_integration()
