# name: measure |11> after two X gates
qubit a[2]
qubitop1 a[0] = X
qubitop1 a[1] = X
measure a
print(a)
end
