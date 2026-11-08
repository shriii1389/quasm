# name: so is measuring the whole of one, rather than inventing |00>
# expect_error: Cannot measure a register with zero norm
qubit a = [(0,0),(0,0),(0,0),(0,0)]
measure a
end
