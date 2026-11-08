# name: measuring a qubit of an all-zero register is an error, not NaN
# expect_error: Cannot measure a register with zero norm
qubit a = [(0,0),(0,0)]
measure a[0]
end
