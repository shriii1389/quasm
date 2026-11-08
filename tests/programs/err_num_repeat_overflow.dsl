# name: a loop count past 2^32 is out of range, not wrapped to 0
# expect_error: Number out of range
qubit q[1]
repeat 4294967296
qubitop1 q[0] = X
endrepeat
end
