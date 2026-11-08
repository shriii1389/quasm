# name: whole-register measurement of the maximum 6-qubit register
qubit a[6]
qubitop1 a[0] = H
qubitop1 a[5] = H
measure a
print(a)
end
