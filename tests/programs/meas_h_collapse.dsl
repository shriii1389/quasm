# name: H then measure, collapsed state renormalised to 1
qubit a[1]
qubitop1 a[0] = H
print(a)
measure a[0]
print(a)
end
