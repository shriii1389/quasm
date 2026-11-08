# an error inside a conditional inside a loop is reported once, not six times
# expect_error: Qubit index out of range
# expect_count: 1 Qubit index out of range
set c = 1
qubit a[1]
repeat 6
if c == 1
qubitop1 a[9] = X
endif
endrepeat
print(a)
end
