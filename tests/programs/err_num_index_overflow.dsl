# name: a qubit index past 2^32 is out of range, not wrapped to qubit 1
# expect_error: Number out of range
qubit q[2]
qubitop1 q[4294967297] = X
end
