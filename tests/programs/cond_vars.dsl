# name: comparing two classical variables, one set from the other
set a = 6
set b = a
qubit q[1]
if a == b
qubitop1 q[0] = H
endif
set b = 2
if a == b
qubitop1 q[0] = X
endif
print(q)
end
