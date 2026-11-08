# H then X then H is Z
qubit a = [(0.6,0.25),(0.3,-0.7)]
qubitop1 a[0] = H
qubitop1 a[0] = X
qubitop1 a[0] = H
print(a)
end
