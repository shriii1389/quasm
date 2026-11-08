# name: a true condition runs the branch
set c = 1
qubit a[2]
if c == 1
qubitop1 a[0] = H
qubitop2 a[0],a[1] = CN
endif
print(a)
end
