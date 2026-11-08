# name: a false condition skips the branch entirely
set c = 0
qubit a[1]
if c == 1
qubitop1 a[0] = X
qubitop1 a[0] = H
endif
print(a)
end
