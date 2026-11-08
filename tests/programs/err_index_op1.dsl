# single-qubit gate on a qubit past the end of the register
# expect_error: Qubit index out of range
qubit q[2]
qubitop1 q[2] = H
end
