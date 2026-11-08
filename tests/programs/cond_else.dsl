# name: else runs when the if does not
set c = 0
qubit a[1]
if c == 1
qubitop1 a[0] = X
else
qubitop1 a[0] = H
endif
print(a)
end
