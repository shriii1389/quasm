# name: a measured index past 2^32 is out of range
# expect_error: Number out of range
qubit q[2]
measure q[4294967297]
end
