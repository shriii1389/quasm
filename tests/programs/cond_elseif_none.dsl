# name: no branch matches and there is no else
set c = 9
qubit a[1]
qubitop1 a[0] = H
if c == 1
qubitop1 a[0] = X
else if c == 2
qubitop1 a[0] = Y
endif
print(a)
end
