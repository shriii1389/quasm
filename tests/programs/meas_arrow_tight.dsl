# name: the arrow needs no space on either side: measure q[0]->c
qubit q[2]
qubitop1 q[0] = X
measure q[0]->c
measure q->d
qubit r[1]
if c == 1
qubitop1 r[0] = X
endif
if d == 2
qubitop1 r[0] = H
endif
print(r)
end
