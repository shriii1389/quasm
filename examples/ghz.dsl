# A GHZ state on three qubits: (|000> + |111>)/sqrt(2).
qubit q[3]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
qubitop2 q[1],q[2] = CN
print(q)

# Measuring one qubit decides all three.
measure q[0]
print(q)
measure q
end
