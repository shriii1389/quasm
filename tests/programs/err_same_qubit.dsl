# a two-qubit gate naming one qubit twice
# expect_error: Two-qubit gate needs two distinct qubits
qubit q[2]
qubitop2 q[0],q[0] = CN
end
