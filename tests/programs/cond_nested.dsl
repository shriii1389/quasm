# name: an if inside a taken branch
set c = 2
set d = 3
qubit a[2]
if c == 2
if d == 3
qubitop1 a[0] = H
else
qubitop1 a[0] = X
endif
qubitop2 a[0],a[1] = CN
else
qubitop1 a[1] = Y
endif
print(a)
end
