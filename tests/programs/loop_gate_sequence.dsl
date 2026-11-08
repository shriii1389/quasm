# name: a loop building a GHZ state one qubit at a time
qubit a[4]
qubitop1 a[0] = H
qubitop2 a[0],a[1] = CN
repeat 2
qubitop2 a[1],a[2] = CN
endrepeat
qubitop2 a[0],a[3] = CN
print(a)
end
