# name: measure and correct inside a loop, so the state is |0> every time
seed 31
qubit a[1]
repeat 8
qubitop1 a[0] = H
measure a[0] -> c
if c == 1
qubitop1 a[0] = X
endif
print(a)
endrepeat
end
