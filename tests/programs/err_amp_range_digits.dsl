# name: a 42-digit amplitude is out of range, not silently read as 0
# expect_error: Number out of range
qubit a = [(100000000000000000000000000000000000000000,0),(1,0)]
end
