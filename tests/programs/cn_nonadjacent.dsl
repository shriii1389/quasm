# CNOT across non-adjacent qubits of a 3-qubit register
qubit q[3]
qubitop1 q[0] = H
qubitop1 q[1] = H
qubitop1 q[2] = H
qubitop1 q[1] = T
qubitop2 q[0],q[2] = CN
print(q)
end
