# name: a two-qubit target index past 2^32 is out of range
# expect_error: Number out of range
qubit q[2]
qubitop2 q[0],q[4294967297] = CN
end
