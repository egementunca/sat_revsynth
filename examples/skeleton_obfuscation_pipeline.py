#!/usr/bin/env python3
"""Example: Skeleton Chain Obfuscation Pipeline

This script demonstrates the complete workflow for skeleton chain synthesis
and limited unrolling for circuit obfuscation:

1. Synthesize a skeleton chain (identity circuit with collision constraints)
2. Verify skeleton properties
3. Estimate equivalence class size
4. Generate bounded equivalents via limited unrolling
5. Save results for obfuscation use

Usage:
    python examples/skeleton_obfuscation_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from synthesizers.skeleton_chain_api import (
    synthesize_skeleton_chain,
    limited_unroll,
    verify_skeleton_chain,
    estimate_unroll_size,
)


def demo_small_circuit():
    """Demo with a small circuit (4 wires, 8 gates)."""
    print("\n" + "=" * 70)
    print("DEMO 1: Small Skeleton Chain (4 wires, 8 gates)")
    print("=" * 70)

    # Synthesize
    print("\n[Step 1] Synthesizing skeleton chain...")
    skeleton = synthesize_skeleton_chain(wires=4, gates=8)

    if skeleton is None:
        skeleton = synthesize_skeleton_chain(wires=4, gates=10)

    if skeleton is None:
        print("❌ Could not synthesize skeleton chain")
        return

    print(f"✓ Synthesized {len(skeleton)} gates on {skeleton._width} wires")

    # Verify
    print("\n[Step 2] Verifying skeleton properties...")
    is_skeleton = verify_skeleton_chain(skeleton)
    is_identity = skeleton.is_identity()

    print(f"  Skeleton chain: {'✓' if is_skeleton else '✗'}")
    print(f"  Identity function: {'✓' if is_identity else '✗'}")

    # Estimate
    print("\n[Step 3] Estimating equivalence class size...")
    est = estimate_unroll_size(skeleton._width, len(skeleton), is_skeleton=True)
    print(f"  Total permutations: {est['permutations']:,}")
    print(f"  Estimated full unroll: {est['total_estimate']:,} circuits")
    print(f"  Recommended sampling: {est['recommended_max_permutations']} permutations")

    # Limited unroll
    print("\n[Step 4] Generating 100 equivalent circuits...")
    variants = limited_unroll(
        skeleton,
        max_circuits=100,
        max_permutations=10,
        use_skeleton_mode=True,
    )

    print(f"✓ Generated {len(variants):,} circuits")

    # Verify a few variants are identities
    print("\n[Step 5] Verifying variant circuits...")
    for i, v in enumerate(variants[:5]):
        is_id = v.is_identity()
        print(f"  Variant {i+1}: {'✓ identity' if is_id else '✗ not identity'}")

    print("\n✓ Demo 1 complete!")


def demo_medium_circuit():
    """Demo with a medium circuit (8 wires, 16 gates)."""
    print("\n" + "=" * 70)
    print("DEMO 2: Medium Skeleton Chain (8 wires, 16 gates)")
    print("=" * 70)

    print("\n[Step 1] Synthesizing skeleton chain...")
    skeleton = synthesize_skeleton_chain(wires=8, gates=16)

    if skeleton is None:
        print("❌ Could not synthesize skeleton chain (trying more gates...)")
        skeleton = synthesize_skeleton_chain(wires=8, gates=20)

    if skeleton is None:
        print("❌ Could not synthesize - skipping demo 2")
        return

    print(f"✓ Synthesized {len(skeleton)} gates on {skeleton._width} wires")

    # Estimate
    print("\n[Step 2] Estimating equivalence class size...")
    est = estimate_unroll_size(skeleton._width, len(skeleton), is_skeleton=True)
    print(f"  Total permutations: {est['permutations']:,}")
    print(f"  Estimated full unroll: {est['total_estimate']:,} circuits")

    if est['total_estimate'] > 1_000_000:
        print("  ⚠ Warning: Full unroll would generate >1M circuits!")

    # Limited unroll with sampling
    print("\n[Step 3] Generating 500 circuits (sampling 50 permutations)...")
    variants = limited_unroll(
        skeleton,
        max_circuits=500,
        max_permutations=50,  # Sample instead of enumerating all 8! = 40,320
        use_skeleton_mode=True,
    )

    print(f"✓ Generated {len(variants):,} circuits")
    print(f"  Memory saved: ~{est['total_estimate'] - len(variants):,} circuits not generated")

    print("\n✓ Demo 2 complete!")


def demo_large_circuit_safe():
    """Demo showing how to safely handle large circuits."""
    print("\n" + "=" * 70)
    print("DEMO 3: Large Skeleton Chain (12 wires, 24 gates) - Safe Mode")
    print("=" * 70)

    print("\n[Step 1] Checking if synthesis is feasible...")
    est = estimate_unroll_size(wires=12, gates=24, is_skeleton=True)
    print(f"  Estimated full unroll: {est['total_estimate']:,} circuits")

    if not est['is_feasible_full_unroll']:
        print("  ⚠ Full unroll NOT feasible - will use limited unrolling")

    print("\n[Step 2] Synthesizing skeleton chain...")
    # Note: This might take a while or be UNSAT
    skeleton = synthesize_skeleton_chain(wires=12, gates=24)

    if skeleton is None:
        print("❌ Could not synthesize large skeleton (expected - SAT may timeout)")
        print("   Recommendation: Use smaller dimensions or more gates")
        return

    print(f"✓ Synthesized {len(skeleton)} gates on {skeleton._width} wires")

    # LIMITED unroll only (never do full unroll on large circuits!)
    print("\n[Step 3] Generating 1000 circuits with strict limits...")
    variants = limited_unroll(
        skeleton,
        max_circuits=1000,
        max_permutations=100,  # Sample 100 out of 12! = 479,001,600
        use_skeleton_mode=True,
    )

    print(f"✓ Generated {len(variants):,} circuits")
    reduction_factor = est['total_estimate'] / len(variants) if len(variants) > 0 else 0
    print(f"  Reduction factor: {reduction_factor:,.0f}× (avoided memory explosion!)")

    print("\n✓ Demo 3 complete!")


def demo_obfuscation_workflow():
    """Demo showing practical obfuscation use case."""
    print("\n" + "=" * 70)
    print("DEMO 4: Practical Obfuscation Workflow")
    print("=" * 70)

    print("\nScenario: Generate identity circuits for runtime obfuscation")
    print("Goal: Create a pool of 200 diverse identity circuits")

    print("\n[Step 1] Synthesizing base skeleton...")
    skeleton = synthesize_skeleton_chain(wires=6, gates=12)

    if skeleton is None:
        skeleton = synthesize_skeleton_chain(wires=6, gates=14)

    if skeleton is None:
        print("❌ Could not synthesize skeleton")
        return

    print(f"✓ Base skeleton: {len(skeleton)} gates")

    print("\n[Step 2] Generating obfuscation pool...")
    pool = limited_unroll(
        skeleton,
        max_circuits=200,
        max_permutations=20,
        use_skeleton_mode=True,
    )

    print(f"✓ Pool size: {len(pool)} unique identity circuits")

    print("\n[Step 3] Analyzing pool diversity...")
    # Check diversity by looking at first few gates
    first_gates = set()
    for circ in pool:
        gates = list(circ.gates())
        if gates:
            first_gates.add((gates[0].target, gates[0].ctrl1, gates[0].ctrl2))

    print(f"  Unique first gates: {len(first_gates)}")
    print(f"  Diversity ratio: {len(first_gates)/len(pool)*100:.1f}%")

    print("\n[Step 4] Usage recommendation...")
    print("  💡 At runtime: Pick random circuit from pool to obfuscate operations")
    print("  💡 All circuits are identities: input = output (but hard to analyze)")
    print("  💡 Collision structure prevents simple optimization attacks")

    print("\n✓ Demo 4 complete!")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("SKELETON CHAIN OBFUSCATION PIPELINE - EXAMPLES")
    print("=" * 70)

    try:
        # Demo 1: Small circuit (quick)
        demo_small_circuit()

        # Demo 2: Medium circuit (moderate)
        demo_medium_circuit()

        # Demo 3: Large circuit (showing safe limits)
        demo_large_circuit_safe()

        # Demo 4: Practical obfuscation use case
        demo_obfuscation_workflow()

    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("ALL DEMOS COMPLETE")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("1. Skeleton chains have all adjacent gates colliding")
    print("2. Limited unrolling prevents memory explosion on large circuits")
    print("3. Sampling permutations reduces equivalence class from billions to thousands")
    print("4. All generated circuits are identities (verified by truth table)")
    print("5. Use skeleton_chain_api for high-level synthesis and unrolling")


if __name__ == "__main__":
    main()
