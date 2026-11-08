# name: measure index past the end of the register
# expect_error: Qubit index out of range
qubit a[2]
measure a[2]
end
