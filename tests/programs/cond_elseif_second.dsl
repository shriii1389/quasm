# name: a later else-if matches after two misses
set c = 3
qubit a[2]
if c == 1
qubitop1 a[0] = X
else if c == 2
qubitop1 a[0] = Y
else if c == 3
qubitop1 a[1] = H
else
qubitop1 a[0] = Z
endif
print(a)
end
