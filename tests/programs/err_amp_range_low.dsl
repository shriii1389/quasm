# name: a nonzero amplitude below 1e-18 is out of range, however it is written
# expect_error: Number out of range
qubit a = [(0.0000000000000000001,0),(1,0)]
end
