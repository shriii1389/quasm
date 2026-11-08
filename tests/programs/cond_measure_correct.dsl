# name: measure one Bell qubit and correct on the outcome, always ending |00>
qubit a[2]
qubitop1 a[0] = H
qubitop2 a[0],a[1] = CN
measure a[0] -> c
if c == 1
qubitop1 a[0] = X
qubitop1 a[1] = X
endif
print(a)
end
