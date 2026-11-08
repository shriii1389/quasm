# name: Bell pair, the second qubit must agree with the first
qubit a[2]
qubitop1 a[0] = H
qubitop2 a[0],a[1] = CN
measure a[0]
print(a)
measure a[1]
print(a)
end
