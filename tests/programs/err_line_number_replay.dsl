# name: an error on a replayed loop line names that line, not the loop head
# expect_error: Line 7: Qubit index out of range
qubit q[1]
set c = 0
repeat 3
if c == 1
qubitop1 q[5] = X
endif
set c = 1
endrepeat
end
