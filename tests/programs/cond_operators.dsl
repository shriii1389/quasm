# name: all six comparisons, five of which hold
set a = 4
set b = 7
qubit q[1]
if a != b
qubitop1 q[0] = X
endif
if a < b
qubitop1 q[0] = X
endif
if b <= 7
qubitop1 q[0] = X
endif
if b > a
qubitop1 q[0] = X
endif
if a >= 4
qubitop1 q[0] = X
endif
if a == b
qubitop1 q[0] = X
endif
print(q)
end
