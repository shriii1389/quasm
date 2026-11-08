# name: a seed past 2^32 is out of range, not wrapped to the illegal 0
# expect_error: Number out of range
seed 4294967296
end
