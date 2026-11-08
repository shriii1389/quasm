# Branching on a measurement outcome.
#
# Measuring half of a Bell pair collapses it to |00> or |11> with equal
# probability. The `-> c` tail keeps the outcome as a classical 0 or 1, and
# `if` uses it to flip both qubits back when the pair landed on |11>.
#
# So the measurement is genuinely random, and the final state is genuinely
# always |00>. Run it a few times with different seeds and watch the reported
# outcome change while the printed state does not.
qubit q[2]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN

measure q[0] -> c       # |0> or |1>, whichever the PRNG gave
print(q)                # collapsed, but not yet corrected

if c == 1
qubitop1 q[0] = X
qubitop1 q[1] = X
endif

print(q)                # always [(1,0),(0,0),(0,0),(0,0)] -- that is |00>
end
