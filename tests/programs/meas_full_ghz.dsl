# name: GHZ-3 whole-register measurement (only |000> and |111> possible)
qubit a[3]
qubitop1 a[0] = H
qubitop2 a[0],a[1] = CN
qubitop2 a[1],a[2] = CN
measure a
print(a)
end
