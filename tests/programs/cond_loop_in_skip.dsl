# name: a loop inside a skipped branch must not run
set c = 0
qubit a[1]
if c == 1
repeat 3
qubitop1 a[0] = X
endrepeat
else
qubitop1 a[0] = H
endif
print(a)
end
