# name: superdense coding decodes all four two-bit messages with certainty
qubit s[2]
qubitop1 s[0] = H
qubitop2 s[0],s[1] = CN
qubitop2 s[0],s[1] = CN
qubitop1 s[0] = H
measure s
print(s)
qubit s[2]
qubitop1 s[0] = H
qubitop2 s[0],s[1] = CN
qubitop1 s[0] = X
qubitop2 s[0],s[1] = CN
qubitop1 s[0] = H
measure s
print(s)
qubit s[2]
qubitop1 s[0] = H
qubitop2 s[0],s[1] = CN
qubitop1 s[0] = Z
qubitop2 s[0],s[1] = CN
qubitop1 s[0] = H
measure s
print(s)
qubit s[2]
qubitop1 s[0] = H
qubitop2 s[0],s[1] = CN
qubitop1 s[0] = X
qubitop1 s[0] = Z
qubitop2 s[0],s[1] = CN
qubitop1 s[0] = H
measure s
print(s)
end
