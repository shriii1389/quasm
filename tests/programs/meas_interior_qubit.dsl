# name: measure an interior qubit of a 4-qubit register
qubit a[4]
qubitop1 a[1] = H
qubitop1 a[2] = H
measure a[2]
print(a)
end
