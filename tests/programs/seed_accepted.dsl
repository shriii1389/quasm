# name: seed changes the stream without disturbing the state
seed 987654321
qubit a[2]
qubitop1 a[0] = H
qubitop2 a[0],a[1] = CN
measure a
print(a)
end
