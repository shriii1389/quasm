# name: 4294967295 is the largest integer, and it is exact
set c = 4294967295
set d = c
qubit q[1]
if d == 4294967295
qubitop1 q[0] = X
endif
if d > 4294967294
qubitop1 q[0] = H
endif
print(q)
end
