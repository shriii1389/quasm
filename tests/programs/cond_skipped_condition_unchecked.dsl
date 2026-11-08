# name: a condition is only checked when it is evaluated
set c = 1
qubit q[1]
if c == 1
qubitop1 q[0] = X
else if z == 9
qubitop1 q[0] = Y
endif
if c == 0
if y > 3
qubitop1 q[0] = Z
endif
endif
print(q)
end
