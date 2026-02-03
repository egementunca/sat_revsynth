"""Verify generated skeleton files.

Checks:
1. Format parsing (TC1C2)
2. Identity property (using ECA57 logic)
3. Skeleton Chain property (adjacent collision)
"""
import sys
import os

def wire_from_char(c):
    code = ord(c)
    if 48 <= code <= 57: return code - 48
    if 97 <= code <= 122: return code - 97 + 10
    if 65 <= code <= 90: return code - 65 + 36
    return -1

class Gate:
    def __init__(self, t, c1, c2, idx):
        self.t = t
        self.c1 = c1
        self.c2 = c2
        self.idx = idx

    def __str__(self):
        return f"G{self.idx}(T={self.t}, C={{{self.c1}, {self.c2}}})"

def verify_file(filename):
    print(f"Verifying {filename}...")
    gates = []
    max_wire = 0
    
    with open(filename, 'r') as f:
        for i, line in enumerate(f):
            line = line.strip().strip(';')
            if not line: continue
            if len(line) < 3:
                print(f"  [Error] Line {i+1}: '{line}' too short")
                continue
            
            t = wire_from_char(line[0])
            c1 = wire_from_char(line[1])
            c2 = wire_from_char(line[2])
            
            gates.append(Gate(t, c1, c2, i))
            max_wire = max(max_wire, t, c1, c2)

    width = max_wire + 1
    print(f"  Parsed {len(gates)} gates, Width detected: {width}")

    # 1. Check Chain (Collision)
    print("  Checking Chain Property...")
    chain_broken = False
    for i in range(len(gates) - 1):
        g1 = gates[i]
        g2 = gates[i+1]
        
        # Collision: T1 in C2 OR T2 in C1
        c1 = g1.t in [g2.c1, g2.c2]
        c2 = g2.t in [g1.c1, g1.c2]
        
        if not (c1 or c2):
            print(f"    [FAIL] Pair {i}-{i+1} COMMUTE! {g1} vs {g2}")
            chain_broken = True
    
    if not chain_broken:
        print("    [OK] All adjacent gates collide (Valid Chain).")
    else:
        print("    [FAIL] Chain property violated.")

    # 2. Check Identity (ECA57 Logic)
    # Target ^= (C1 | ~C2)
    print("  Checking Identity Property (ECA57)...")
    is_identity = True
    
    # We can simulate all 2^width patterns for small width
    if width <= 10:
        for state in range(1 << width):
            initial = state
            curr = state
            for g in gates:
                # Logic: if (state & (1<<c1)) OR NOT (state & (1<<c2))
                ctrl1_set = (curr >> g.c1) & 1
                ctrl2_set = (curr >> g.c2) & 1
                
                if ctrl1_set or (not ctrl2_set):
                    curr ^= (1 << g.t)
            
            if curr != initial:
                print(f"    [FAIL] Input {bin(initial)} -> {bin(curr)}")
                is_identity = False
                break
        
        if is_identity:
            print("    [OK] Circuit is Identity.")
        else:
            print("    [FAIL] Circuit is NOT Identity.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 verify_skeleton.py <file.gate>")
        sys.exit(1)
    
    verify_file(sys.argv[1])
