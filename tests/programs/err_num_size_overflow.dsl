# name: a register size past 2^32 is out of range, not wrapped to 2
# expect_error: Number out of range
qubit q[4294967298]
end
