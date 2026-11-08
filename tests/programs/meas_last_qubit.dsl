# name: measure the final qubit of a 5-qubit register
qubit a[5]
qubitop1 a[4] = H
qubitop1 a[0] = H
measure a[4]
print(a)
end
