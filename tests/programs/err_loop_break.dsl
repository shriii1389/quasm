# an error inside a loop breaks out of it instead of repeating four times
# expect_error: Qubit index out of range
# expect_count: 1 Qubit index out of range
qubit a[1]
repeat 4
qubitop1 a[9] = X
endrepeat
print(a)
end
