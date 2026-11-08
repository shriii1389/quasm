# name: an if inside a loop body, re-evaluated every iteration
set c = 1
qubit a[1]
repeat 3
if c == 1
qubitop1 a[0] = X
else
qubitop1 a[0] = H
endif
endrepeat
print(a)
end
