# name: a full-precision 1/sqrt(2), as Python prints it, is read correctly
qubit a = [(0.7071067811865476,0),(0.7071067811865476,0)]
qubitop1 a[0] = H
print(a)
end
