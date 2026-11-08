# name: an if inside a skipped branch runs nothing, and its else is not taken
set c = 0
qubit a[1]
if c == 1
if c == 0
qubitop1 a[0] = X
else
qubitop1 a[0] = Y
endif
qubitop1 a[0] = Z
else
qubitop1 a[0] = H
endif
print(a)
end
