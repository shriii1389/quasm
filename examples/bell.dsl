# A Bell pair: H on the first qubit, then CNOT onto the second.
# The result is (|00> + |11>)/sqrt(2) -- the two qubits always agree.
qubit q[2]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
print(q)

measure q          # collapses to |00> or |11>, never |01> or |10>
print(q)
end
