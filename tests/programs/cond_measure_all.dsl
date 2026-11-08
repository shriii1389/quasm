# name: branch on the basis index a whole-register measurement produced
qubit a[3]
qubitop1 a[0] = H
qubitop2 a[0],a[1] = CN
qubitop2 a[1],a[2] = CN
measure a -> c
if c == 0
qubit r[1]
else if c == 7
qubit r[1]
qubitop1 r[0] = X
else
qubit r[2]
endif
print(r)
end
