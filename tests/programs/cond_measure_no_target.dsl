# name: a measurement without an arrow leaves the classical variable alone
set c = 0
qubit a[1]
qubitop1 a[0] = X
measure a[0]
if c == 1
qubitop1 a[0] = H
endif
print(a)
end
