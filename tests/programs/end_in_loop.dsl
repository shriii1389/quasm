# name: end inside a loop stops it on the first pass
qubit q[1]
repeat 3
qubitop1 q[0] = X
print(q)
end
endrepeat
print(q)
end
