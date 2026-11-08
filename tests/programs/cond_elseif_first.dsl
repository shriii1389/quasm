# name: the first matching else-if wins
set c = 5
qubit a[1]
if c == 1
qubitop1 a[0] = X
else if c == 5
qubitop1 a[0] = H
else if c == 5
qubitop1 a[0] = Y
else
qubitop1 a[0] = Z
endif
print(a)
end
