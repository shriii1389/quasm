# name: gates still apply correctly to a partially collapsed register
qubit a[3]
qubitop1 a[0] = H
qubitop2 a[0],a[2] = CN
measure a[0]
qubitop1 a[1] = H
print(a)
end
